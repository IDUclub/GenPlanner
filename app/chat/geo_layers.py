"""
Geo-layer links for the chat stream and the chat history.

A chat generation's zones, roads and territory are written to object storage under a
fresh result id and served back by `GET /genplanner/files/{slot}/{result_id}`. The chat
history keeps only a descriptor (a ChatStorage `file` part), so the frontend can restore
the map from `chat_history` alone.

`url` is always a path relative to this service: the frontend prepends the base address
it knows for `source_service`. A host baked into chat history would be an internal
address the browser behind the external proxy can't reach. `download_url` is always
None -- MinIO sits on a private network, so bytes are streamed through the API instead
of handed out as presigned URLs.
"""

import asyncio
import re
import uuid
from typing import Any, AsyncIterator

from loguru import logger

from app.common.object_storage.object_storage import ObjectStorage, ObjectStorageError

SOURCE_SERVICE = "genplanner"
MIME_TYPE = "application/geo+json"
FILES_PATH = "/genplanner/files"

SLOT_ZONES = "zones"
SLOT_ROADS = "roads"
SLOT_TERRITORY = "territory"

_SLOT_SPECS: dict[str, tuple[str, str]] = {
    SLOT_ZONES: ("Функциональные зоны", "result"),
    SLOT_ROADS: ("Дороги", "result"),
    SLOT_TERRITORY: ("Граница территории", "input"),
}

FILE_SLOTS: tuple[str, ...] = tuple(_SLOT_SPECS)

_RESULT_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def new_result_id() -> str:
    return uuid.uuid4().hex


def is_valid_result_id(result_id: str) -> bool:
    return bool(_RESULT_ID_RE.match(result_id))


def object_key(result_id: str, slot: str) -> str:
    """Storage key for one slot of one generation result, derived from the id alone."""

    if slot not in _SLOT_SPECS:
        raise ValueError(f"Unknown geo-layer slot: {slot!r}")
    if not is_valid_result_id(result_id):
        raise ValueError(f"Invalid result id: {result_id!r}")
    return f"{result_id}/{slot}.geojson"


def build_stored_layer(*, slot: str, result_id: str) -> dict[str, Any]:
    """Descriptor for a layer served from object storage."""

    title, role = _SLOT_SPECS[slot]
    return {
        "name": slot,
        "title": title,
        "role": role,
        "url": f"{FILES_PATH}/{slot}/{result_id}",
        "download_url": None,
        "filename": f"{slot}.geojson",
        "mime_type": MIME_TYPE,
        "source_service": SOURCE_SERVICE,
    }


def geo_layer_to_file_part(layer: dict[str, Any]) -> dict[str, Any]:
    """ChatStorage `file` part payload from a layer descriptor (only the durable `url`)."""

    return {
        "url": layer["url"],
        "name": layer["name"],
        "title": layer["title"],
        "filename": layer["filename"],
        "mime_type": layer["mime_type"],
        "source_service": layer["source_service"],
    }


async def store_result_layers(
    object_storage: ObjectStorage | None,
    result_payload: dict[str, Any],
    file_layers: list[dict[str, Any]],
) -> AsyncIterator[dict[str, Any]]:
    """
    Write zones/roads/territory of `result_payload` to storage and yield a `file` event
    per stored layer. Best-effort: a failed write becomes a `store_layer` warning and the
    slot is skipped -- the live `result` event already carried the layers, only the link
    in history is lost. Stored descriptors are appended to `file_layers` for persistence.
    """

    if object_storage is None:
        return

    result_id = new_result_id()
    for slot in FILE_SLOTS:
        payload = result_payload.get(slot)
        if payload is None:
            continue
        try:
            await asyncio.to_thread(object_storage.put_json, payload, object_key(result_id, slot))
        except (ObjectStorageError, OSError) as exc:
            logger.warning(f"storing layer {slot} failed: {exc}")
            yield {
                "type": "warning",
                "stage": "store_layer",
                "detail": str(exc),
                "message": f"Слой «{slot}» не сохранён — в истории чата его не будет.",
            }
            continue
        descriptor = build_stored_layer(slot=slot, result_id=result_id)
        file_layers.append(descriptor)
        yield {"type": "file", **descriptor}


def assistant_message_parts(reply: str, file_layers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    ChatStorage takes either `content` or `parts`, and layer links only survive as `file`
    parts -- so the reply text goes in as a `text` part next to them.
    """

    parts: list[dict[str, Any]] = []
    if reply:
        parts.append({"kind": "text", "payload": {"text": reply}})
    parts += [{"kind": "file", "payload": geo_layer_to_file_part(layer)} for layer in file_layers]
    return parts
