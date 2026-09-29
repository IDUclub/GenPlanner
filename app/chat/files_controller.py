from typing import Annotated

from fastapi import APIRouter, Depends, Path
from fastapi.responses import StreamingResponse

from app.common.exceptions.http_exception import http_exception
from app.common.object_storage.object_storage import ObjectStorage, ObjectStorageError
from app.dependencies import get_object_storage

from .geo_layers import FILE_SLOTS, MIME_TYPE, is_valid_result_id, object_key

files_router = APIRouter(tags=["chat"])


@files_router.get(
    "/files/{slot}/{result_id}",
    summary="Download a geo layer stored by a chat generation",
    response_class=StreamingResponse,
)
def generation_file(
    slot: Annotated[str, Path(description=f"One of: {', '.join(FILE_SLOTS)}")],
    result_id: Annotated[str, Path(description="Generation result id (uuid4 hex)")],
    storage: ObjectStorage | None = Depends(get_object_storage),
) -> StreamingResponse:
    """
    Stream one layer referenced from the chat history. Bytes go through the API rather
    than a presigned MinIO URL: object storage sits on a private network the frontend
    behind the external proxy can't reach. No bearer: the link is an unguessable result
    id, and history is restored by a plain fetch of the stored `url`.

    Declared `def` on purpose: the storage client is synchronous, so FastAPI runs this in
    a worker thread instead of blocking the event loop.
    """

    if storage is None:
        raise http_exception(
            503, "Layer storage is not configured", _input={"slot": slot, "result_id": result_id}, _detail=None
        )
    if slot not in FILE_SLOTS:
        raise http_exception(404, f"Unknown layer slot '{slot}'", _input={"slot": slot}, _detail=None)
    if not is_valid_result_id(result_id):
        raise http_exception(404, "Unknown generation result", _input={"result_id": result_id}, _detail=None)

    key = object_key(result_id, slot)
    try:
        found = storage.exists(key)
    except ObjectStorageError as exc:
        raise http_exception(
            502, "Layer storage is unavailable", _input={"result_id": result_id}, _detail=str(exc)
        ) from exc
    if not found:
        raise http_exception(
            404, "Layer is no longer available", _input={"slot": slot, "result_id": result_id}, _detail=None
        )

    return StreamingResponse(
        storage.open_stream(key),
        media_type=MIME_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{slot}.geojson"'},
    )
