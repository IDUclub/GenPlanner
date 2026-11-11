"""Replayable SSE runs shared by workers on one host.

Keep this module identical in BuildPlanner, GenPlanner, GenBuilder and PZZ.
SQLite deliberately uses a local filesystem (not an NFS/shared-volume database).
The journal survives worker restarts; execution itself is never restarted/retried.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import sqlite3
import tempfile
import time
from contextlib import asynccontextmanager, closing
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.routing import APIRoute
from sse_starlette.sse import EventSourceResponse, ServerSentEvent
from starlette.routing import request_response

logger = logging.getLogger(__name__)
ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")


def token_owner(token: str) -> str:
    """Use for services that forward tokens without verifying their JWT claims."""
    return "token:" + hashlib.sha256(token.encode()).hexdigest()


def user_owner(user) -> str:
    return "user:" + user.user_id if user.user_id else token_owner(user.token)


async def keycloak_owner(token: str, url: str | None, realm: str | None) -> str:
    """Resolve a verified stable owner for services that otherwise only forward JWTs.

    Userinfo validates the access token at the issuer, so reading an unverified
    JWT sub can never grant replay access. Local setups without Keycloak retain
    exact-token ownership. aiohttp is already a dependency of both callers.
    """
    if not url or not realm:
        return token_owner(token)
    import aiohttp

    endpoint = f"{url.rstrip('/')}/realms/{realm}/protocol/openid-connect/userinfo"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(
                endpoint, headers={"Authorization": f"Bearer {token}"}, allow_redirects=False
            ) as response:
                if response.status in (401, 403):
                    raise HTTPException(401, "Invalid or expired access token")
                if response.status != 200:
                    raise HTTPException(503, "Replay authentication unavailable")
                claims = await response.json()
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        raise HTTPException(503, "Replay authentication unavailable") from exc
    subject = claims.get("sub") if isinstance(claims, dict) else None
    if not isinstance(subject, str) or not subject:
        raise HTTPException(401, "Access token has no user identity")
    return "keycloak:" + endpoint + ":" + subject


def frame(event: str, content: dict) -> bytes:
    return ServerSentEvent(
        event=event, data=json.dumps({"type": event, "content": content}, ensure_ascii=False)
    ).encode()


class Journal:
    def __init__(self, path: str, ttl: int = 900):
        self.path = path
        self.ttl = ttl

    def transact(self, operation):
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute("PRAGMA foreign_keys = ON")
            db.execute(
                "CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, owner TEXT, "
                "path TEXT, status TEXT, touched REAL, bytes INTEGER NOT NULL DEFAULT 0)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS events (run_id TEXT REFERENCES runs(id) "
                "ON DELETE CASCADE, seq INTEGER, data BLOB, PRIMARY KEY(run_id, seq))"
            )
            db.execute("BEGIN IMMEDIATE")
            return operation(db)

    async def call(self, operation):
        return await asyncio.to_thread(self.transact, operation)

    async def claim(self, request_id, owner, path):
        def operation(db):
            db.execute("DELETE FROM runs WHERE touched < ?", (time.time() - self.ttl,))
            row = db.execute("SELECT owner, path FROM runs WHERE id = ?", (request_id,)).fetchone()
            if row:
                if row != (owner, path):
                    raise HTTPException(404, "Request not found")
                return False
            if db.execute("SELECT count(*) FROM runs").fetchone()[0] >= 1000:
                raise HTTPException(503, "Stream journal is full; retry later")
            db.execute("INSERT INTO runs VALUES (?, ?, ?, 'running', ?, 0)", (request_id, owner, path, time.time()))
            return True

        return await self.call(operation)

    async def append(self, request_id, data):
        def operation(db):
            size = db.execute("SELECT bytes FROM runs WHERE id = ?", (request_id,)).fetchone()[0]
            if size + len(data) > 64 * 1024 * 1024:
                raise RuntimeError("SSE replay journal limit exceeded")
            seq = db.execute("SELECT coalesce(max(seq), 0) + 1 FROM events WHERE run_id = ?", (request_id,)).fetchone()[
                0
            ]
            db.execute("INSERT INTO events VALUES (?, ?, ?)", (request_id, seq, data))
            db.execute(
                "UPDATE runs SET touched = ?, bytes = bytes + ? WHERE id = ?", (time.time(), len(data), request_id)
            )

        await self.call(operation)

    async def touch(self, request_id):
        await self.call(lambda db: db.execute("UPDATE runs SET touched = ? WHERE id = ?", (time.time(), request_id)))

    async def finish(self, request_id, status):
        await self.call(
            lambda db: db.execute(
                "UPDATE runs SET status = ?, touched = ? WHERE id = ?", (status, time.time(), request_id)
            )
        )

    async def discard(self, request_id):
        await self.call(lambda db: db.execute("DELETE FROM runs WHERE id = ?", (request_id,)))

    async def read(self, request_id, owner, after):
        def operation(db):
            row = db.execute("SELECT owner, status, touched FROM runs WHERE id = ?", (request_id,)).fetchone()
            if not row or row[0] != owner or row[2] < time.time() - self.ttl:
                raise HTTPException(404, "Request not found or expired")
            status = row[1]
            if status == "running" and row[2] < time.time() - 60:
                status = "interrupted"
                seq = db.execute("SELECT coalesce(max(seq), 0) FROM events WHERE run_id = ?", (request_id,)).fetchone()[
                    0
                ]
                for event, content in (
                    ("error", {"message": "Request worker stopped", "request_id": request_id}),
                    ("done", {"status": status, "request_id": request_id}),
                ):
                    seq += 1
                    db.execute("INSERT INTO events VALUES (?, ?, ?)", (request_id, seq, frame(event, content)))
                db.execute("UPDATE runs SET status = ?, touched = ? WHERE id = ?", (status, time.time(), request_id))
            events = db.execute(
                "SELECT seq, data FROM events WHERE run_id = ? AND seq > ? " "ORDER BY seq LIMIT 100",
                (request_id, after),
            ).fetchall()
            last = db.execute("SELECT coalesce(max(seq), 0) FROM events WHERE run_id = ?", (request_id,)).fetchone()[0]
            if after > last:
                raise HTTPException(422, "Cursor exceeds the last event")
            return status, events

        return await self.call(operation)


class Streams:
    def __init__(self, journal):
        self.journal = journal
        self.tasks = set()

    async def heartbeat(self, request_id):
        while True:
            await self.journal.touch(request_id)
            await asyncio.sleep(5)

    async def produce(self, request_id, response):
        heartbeat = asyncio.create_task(self.heartbeat(request_id))
        status = "done"
        try:
            await self.journal.append(request_id, frame("pipeline_started", {"request_id": request_id}))
            async for item in response.body_iterator:
                if isinstance(item, ServerSentEvent):
                    data = item.encode()
                elif isinstance(item, dict):
                    data = ServerSentEvent(**item).encode()
                elif isinstance(item, bytes):
                    data = item
                else:
                    data = ServerSentEvent(data=str(item)).encode()
                await self.journal.append(request_id, data)
            if response.background:
                await response.background()
        except (Exception, asyncio.CancelledError):
            logger.exception("SSE producer failed: %s", request_id)
            status = "interrupted"

            # Reserve space for terminal events even if the normal event limit was hit.
            def failed(db):
                seq = db.execute("SELECT coalesce(max(seq), 0) FROM events WHERE run_id = ?", (request_id,)).fetchone()[
                    0
                ]
                for event, content in (
                    ("error", {"message": "Stream execution interrupted", "request_id": request_id}),
                    ("done", {"status": status, "request_id": request_id}),
                ):
                    seq += 1
                    db.execute("INSERT INTO events VALUES (?, ?, ?)", (request_id, seq, frame(event, content)))

            await self.journal.call(failed)
        finally:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)
            try:
                if hasattr(response.body_iterator, "aclose"):
                    await response.body_iterator.aclose()
            finally:
                await self.journal.finish(request_id, status)

    def start(self, request_id, response):
        task = asyncio.create_task(self.produce(request_id, response))
        self.tasks.add(task)

        def completed(task):
            self.tasks.discard(task)
            if not task.cancelled() and task.exception() is not None:
                logger.error("SSE journal failed: %s", request_id, exc_info=task.exception())

        task.add_done_callback(completed)

    async def close(self):
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def response(self, request_id, owner, after, headers=None):
        # Validate before sending HTTP 200, including unknown/foreign/expired ids.
        await self.journal.read(request_id, owner, after)

        async def events():
            cursor = after
            while True:
                status, rows = await self.journal.read(request_id, owner, cursor)
                for seq, data in rows:
                    # The journal's sequence is the only replay cursor.
                    data = re.sub(rb"(?m)^id:[^\r\n]*(?:\r\n|\r|\n)", b"", data)
                    yield f"id: {seq}\r\n".encode() + data
                    cursor = seq
                if not rows and status != "running":
                    return
                if not rows:
                    await asyncio.sleep(0.2)

        outgoing = dict(headers or {})
        outgoing.pop("content-length", None)
        outgoing.update({"X-Request-ID": request_id, "X-Accel-Buffering": "no"})
        return EventSourceResponse(events(), headers=outgoing)


def cursor(request: Request) -> int:
    value = request.query_params.get("after", request.headers.get("last-event-id", "0"))
    if not re.fullmatch(r"[0-9]{1,18}", value):
        raise HTTPException(422, "Invalid SSE cursor")
    return int(value)


def install_resumable_streams(app, *, service, prefix, authenticate):
    """Wrap existing POST SSE routes, preserving their endpoint/auth dependencies.

    authenticate(Request) must verify the caller according to the host service's
    existing policy and return a stable, non-secret owner key.
    """
    path = os.getenv("SSE_REPLAY_DB", str(Path(tempfile.gettempdir()) / f"{service}-sse.sqlite3"))
    streams = Streams(Journal(path, ttl=max(120, int(os.getenv("SSE_REPLAY_TTL", "900")))))

    def wrap(original):
        async def run(request: Request):
            owner = await authenticate(request)
            request_id = request.query_params.get("request_id") or request.headers.get("x-request-id")
            if request_id is None:
                content_type = request.headers.get("content-type", "")
                if "application/json" in content_type:
                    try:
                        body = await request.json()
                    except (ValueError, UnicodeDecodeError):
                        body = None
                    if isinstance(body, dict):
                        request_id = body.get("request_id")
                elif "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
                    request_id = (await request.form()).get("request_id")
            if request_id is not None and (not isinstance(request_id, str) or not ID_PATTERN.fullmatch(request_id)):
                raise HTTPException(422, "Invalid request_id")
            request_id = request_id or str(uuid4())
            after = cursor(request)
            created = await streams.journal.claim(request_id, owner, request.url.path)
            if created:
                if after:
                    await streams.journal.discard(request_id)
                    raise HTTPException(404, "Request not found")
                heartbeat = asyncio.create_task(streams.heartbeat(request_id))
                try:
                    response = await original(request)
                except BaseException:
                    await streams.journal.discard(request_id)
                    raise
                finally:
                    heartbeat.cancel()
                    await asyncio.gather(heartbeat, return_exceptions=True)
                if not isinstance(response, EventSourceResponse):
                    await streams.journal.discard(request_id)
                    return response
                request.state.resumable_stream = True
                streams.start(request_id, response)
                return await streams.response(request_id, owner, after, response.headers)
            return await streams.response(request_id, owner, after)

        async def handler(request: Request):
            try:
                return await run(request)
            finally:
                # Includes reconnects/invalid ids parsed from multipart forms.
                await request.close()

        return handler

    for route in app.routes:
        if (
            isinstance(route, APIRoute)
            and "POST" in route.methods
            and ("/chat/stream" in route.path or route.path.endswith("/run/stream"))
        ):
            route.app = request_response(wrap(route.get_route_handler()))
            route.openapi_extra = {
                **(route.openapi_extra or {}),
                "parameters": [
                    {
                        "name": "request_id",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "string", "pattern": "^[A-Za-z0-9_-]{1,128}$"},
                        "description": "Client run id. Reuse to reconnect without executing again.",
                    },
                    {
                        "name": "after",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "integer", "minimum": 0, "default": 0},
                        "description": "Replay events strictly after this SSE id (or use Last-Event-ID).",
                    },
                ],
            }

    router = APIRouter(prefix=prefix, tags=["requests"])

    async def authenticated_owner(request: Request):
        return await authenticate(request)

    @router.get("/requests/{request_id}/stream", response_class=EventSourceResponse)
    async def reconnect(
        request: Request, request_id: str, after: int = Query(0, ge=0), owner: str = Depends(authenticated_owner)
    ):
        """Replay a run, then follow live events; no files or original body needed."""
        return await streams.response(request_id, owner, cursor(request))

    app.include_router(router)
    previous_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with previous_lifespan(application) as state:
            try:
                yield state
            finally:
                await streams.close()

    app.router.lifespan_context = lifespan
    return streams
