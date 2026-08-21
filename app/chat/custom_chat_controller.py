import json
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sse_starlette.sse import EventSourceResponse

from app.common.auth.bearer import verify_bearer_token
from app.common.auth.user_identity import extract_user_id
from app.common.exceptions.http_exception import http_exception
from app.common.geometries_dto.geometries import PolygonalFeatureCollection
from app.common.geometries_dto.territory_file import parse_territory_file
from app.dependencies import get_chat_storage_client, get_genplanner_service, get_llm_chat_client
from app.gen_planner.gen_planner_service import GenPlannerService

from .custom_chat_service import stream_custom_chat_turn
from .dto.chat_custom_dto import ChatCustomTurnDTO

custom_chat_router = APIRouter(tags=["chat"])


async def _as_sse_events(envelopes: AsyncIterator[dict[str, Any]]) -> AsyncIterator[dict[str, str]]:
    """Wrap gMART-style envelopes into the dict shape sse_starlette expects (event/data)."""

    async for envelope in envelopes:
        yield {"event": envelope.get("type", "message"), "data": json.dumps(envelope, ensure_ascii=False)}


@custom_chat_router.post("/custom/chat/stream")
async def custom_chat_stream(
    request: Request,
    user_query: str = Form(...),
    chat_id: str | None = Form(None),
    territory_file: UploadFile | None = File(None),
    token: str = Depends(verify_bearer_token),
) -> EventSourceResponse:
    """
    Run one turn of the GenPlanner chat agent on a custom (no scenario_id/project_id)
    territory over SSE. Bearer required for user identification/ChatStorage only -- Urban
    API is never called in this flow. `territory_file` (GeoJSON/.zip Shapefile/KML) is
    required on the first message of a chat; later messages of the same chat_id reuse the
    boundary stored on the first turn.
    """

    territory: PolygonalFeatureCollection | None = None
    if territory_file is not None:
        territory = await parse_territory_file(territory_file)

    genplanner_service: GenPlannerService = get_genplanner_service(request)
    llm_client = get_llm_chat_client(request)
    if llm_client is None:
        raise http_exception(
            503,
            "Chat feature is not configured",
            _input={"chat_id": chat_id},
            _detail={"reason": "VLLM_BASE_URL/CHAT_MODEL is not set"},
        )

    chat_storage_client = get_chat_storage_client(request)
    user_id = extract_user_id(token)

    envelopes = stream_custom_chat_turn(
        llm_client=llm_client,
        chat_storage_client=chat_storage_client,
        genplanner_service=genplanner_service,
        user_id=user_id,
        territory=territory,
        params=ChatCustomTurnDTO(user_query=user_query, chat_id=chat_id),
    )
    return EventSourceResponse(_as_sse_events(envelopes))
