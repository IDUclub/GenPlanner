"""Transport-level reconnect tests; no LLM, database or external services."""

import asyncio
import json

import httpx
import pytest
from fastapi import FastAPI, Form, HTTPException, Request
from sse_starlette.sse import AppStatus, EventSourceResponse, ServerSentEvent

from app.resumable_streams import Journal, Streams, install_resumable_streams, token_owner


@pytest.fixture
def setup(monkeypatch, tmp_path):
    monkeypatch.setattr(AppStatus, "should_exit_event", None)
    monkeypatch.setenv("SSE_REPLAY_DB", str(tmp_path / "replay.sqlite3"))
    app = FastAPI()
    calls = []
    release = asyncio.Event()
    release.set()

    async def owner(request):
        token = request.headers.get("authorization")
        if not token:
            raise HTTPException(403)
        return token_owner(token)

    @app.post("/chat/stream")
    async def chat(request: Request, user_query: str = Form(...)):
        calls.append(user_query)

        async def source():
            yield {"event": "chunk", "data": json.dumps({"text": user_query})}
            await release.wait()
            if user_query == "fail":
                raise ValueError("private exception detail")
            # PZZ checks request.state before honoring a transport disconnect.
            assert request.state.resumable_stream
            yield ServerSentEvent(event="done", data="{}")

        return EventSourceResponse(source())

    @app.post("/anonymous/stream")
    async def anonymous():
        return EventSourceResponse(iter([{"event": "done", "data": "{}"}]))

    streams = install_resumable_streams(app, service="test", prefix="", authenticate=owner)
    return app, streams, calls, release


def client(app, token="one"):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers={"Authorization": token}
    )


@pytest.mark.asyncio
async def test_replay_and_cursor_without_original_body(setup):
    app, streams, calls, _ = setup
    async with client(app) as http:
        original = await http.post("/chat/stream?request_id=run-1", data={"user_query": "hello"})
        replay = await http.post("/chat/stream?request_id=run-1")
        assert original.status_code == replay.status_code == 200
        assert original.text == replay.text
        assert original.headers["x-request-id"] == "run-1"
        assert '"request_id": "run-1"' in original.text
        assert original.text.index("pipeline_started") < original.text.index("chunk")
        tail = await http.get("/requests/run-1/stream", headers={"Last-Event-ID": "2"})
        assert "event: done" in tail.text and "event: chunk" not in tail.text
        assert (await http.get("/requests/run-1/stream?after=3")).text == ""
        assert (await http.get("/requests/run-1/stream?after=999")).status_code == 422
        assert (await http.get("/requests/run-1/stream?after=-1")).status_code == 422
    assert calls == ["hello"]
    await streams.close()


@pytest.mark.asyncio
async def test_generated_id_and_form_id(setup):
    app, streams, calls, _ = setup
    async with client(app) as http:
        first = await http.post("/chat/stream", data={"user_query": "hello"})
        request_id = first.headers["x-request-id"]
        assert (await http.get(f"/requests/{request_id}/stream")).text == first.text
        response = await http.post("/chat/stream", data={"request_id": "form-id", "user_query": "form"})
        replay = await http.post("/chat/stream", data={"request_id": "form-id"})
        assert response.text == replay.text
    assert calls == ["hello", "form"]
    await streams.close()


@pytest.mark.asyncio
async def test_auth_validation_and_non_chat_compatibility(setup):
    app, streams, calls, _ = setup
    async with client(app) as http:
        assert (await http.post("/chat/stream?request_id=bad!", data={"user_query": "x"})).status_code == 422
        assert (await http.post("/chat/stream?after=1&request_id=missing")).status_code == 404
        assert (await http.post("/chat/stream?request_id=validation")).status_code == 422
        valid = await http.post("/chat/stream?request_id=validation", data={"user_query": "x"})
        assert valid.status_code == 200
        assert (await http.get("/requests/unknown/stream")).status_code == 404
        assert (await http.get("/requests/validation/stream", headers={"Authorization": "two"})).status_code == 404
        assert (
            await http.post("/chat/stream?request_id=validation", headers={"Authorization": "two"})
        ).status_code == 404
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        assert (await http.get("/requests/validation/stream")).status_code == 403
        assert (await http.post("/anonymous/stream")).status_code == 200
    assert calls == ["x"]
    await streams.close()


@pytest.mark.asyncio
async def test_disconnect_does_not_cancel_producer(setup):
    app, streams, calls, release = setup
    release.clear()
    disconnected = asyncio.Event()
    sent = []
    body = b"user_query=hello"
    received = False

    async def receive():
        nonlocal received
        if not received:
            received = True
            return {"type": "http.request", "body": body, "more_body": False}
        await disconnected.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)
        if message["type"] == "http.response.body" and b"event: chunk" in message.get("body", b""):
            disconnected.set()

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/chat/stream",
        "root_path": "",
        "query_string": b"request_id=disconnect",
        "server": ("test", 80),
        "client": ("client", 1),
        "headers": [(b"authorization", b"one"), (b"content-type", b"application/x-www-form-urlencoded")],
    }
    await asyncio.wait_for(app(scope, receive, send), timeout=3)
    assert streams.tasks
    # A concurrent repeat attaches to the same run; it doesn't invoke the endpoint.
    async with client(app) as http:
        reconnect = asyncio.create_task(http.post("/chat/stream?request_id=disconnect"))
        await asyncio.sleep(0.05)
        assert calls == ["hello"]
        release.set()
        replay = await asyncio.wait_for(reconnect, timeout=3)
        assert "event: chunk" in replay.text and "event: done" in replay.text
    assert calls == ["hello"]
    await streams.close()


@pytest.mark.asyncio
async def test_worker_shared_claim_and_interrupted_run(setup):
    _, streams, _, _ = setup
    other = Journal(streams.journal.path)
    results = await asyncio.gather(
        streams.journal.claim("shared", "owner", "/chat/stream"), other.claim("shared", "owner", "/chat/stream")
    )
    assert sorted(results) == [False, True]
    await other.call(lambda db: db.execute("UPDATE runs SET touched = touched - 61 WHERE id = 'shared'"))
    status, events = await streams.journal.read("shared", "owner", 0)
    assert status == "interrupted"
    assert [seq for seq, _ in events] == [1, 2]
    assert b"event: error" in events[0][1] and b"event: done" in events[1][1]
    assert (await other.read("shared", "owner", 0))[1] == events
    await other.call(lambda db: db.execute("UPDATE runs SET touched = 0 WHERE id = 'shared'"))
    with pytest.raises(HTTPException) as exc:
        await streams.journal.read("shared", "owner", 0)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_failure_is_replayed_without_second_execution(setup):
    app, streams, calls, _ = setup
    async with client(app) as http:
        response = await http.post("/chat/stream?request_id=failure", data={"user_query": "fail"})
        replay = await http.get("/requests/failure/stream")
    assert response.text == replay.text
    assert "event: error" in response.text and "event: done" in response.text
    assert "private exception detail" not in response.text
    assert calls == ["fail"]
    await streams.close()


@pytest.mark.asyncio
async def test_json_id_and_replay_from_another_worker(setup):
    app, streams, calls, _ = setup

    @app.post("/json/chat/stream")
    async def json_chat(payload: dict):
        calls.append(payload["user_query"])
        return EventSourceResponse(iter([{"event": "done", "data": "{}"}]))

    # Install after adding routes, just as each production main module does.
    other = install_resumable_streams(app, service="json-test", prefix="/json", authenticate=lambda_owner)
    async with client(app) as http:
        initial = await http.post("/json/chat/stream", json={"request_id": "json-id", "user_query": "json"})
        replay = await http.post("/json/chat/stream", json={"request_id": "json-id"})
    assert initial.status_code == 200 and initial.text == replay.text
    assert calls == ["json"]
    # Fresh manager, same file: no in-memory state or live producer is required.
    fresh = Streams(Journal(streams.journal.path))
    response = await fresh.response("json-id", token_owner("one"), 0)
    encoded = b"".join([part async for part in response.body_iterator])
    assert encoded.decode() == initial.text
    await other.close()
    await streams.close()


async def lambda_owner(request):
    return token_owner(request.headers["authorization"])


@pytest.mark.asyncio
async def test_shutdown_records_terminal_error(setup):
    app, streams, _, release = setup
    release.clear()
    async with client(app) as http:
        pending = asyncio.create_task(http.post("/chat/stream?request_id=shutdown", data={"user_query": "x"}))
        for _ in range(100):
            if streams.tasks:
                break
            await asyncio.sleep(0.01)
        assert streams.tasks
        await streams.close()
        result = await asyncio.wait_for(pending, 3)
        assert "event: error" in result.text and "event: done" in result.text
        assert not streams.tasks


@pytest.mark.asyncio
async def test_journal_limit_is_enforced_without_large_allocation(setup):
    _, streams, _, _ = setup
    await streams.journal.claim("full", "owner", "/chat/stream")
    await streams.journal.call(
        lambda db: db.execute("UPDATE runs SET bytes = ? WHERE id = 'full'", (64 * 1024 * 1024,))
    )
    with pytest.raises(RuntimeError, match="limit exceeded"):
        await streams.journal.append("full", b"too large")
