import json
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, Request
from iduconfig import Config
from sse_starlette.sse import EventSourceResponse

from app.common.auth.bearer import verify_bearer_token
from app.common.auth.user_identity import extract_user_id
from app.common.exceptions.http_exception import http_exception
from app.dependencies import get_chat_storage_client, get_config, get_genplanner_service, get_llm_chat_client
from app.gen_planner.gen_planner_service import GenPlannerService

from .chat_service import stream_chat_turn
from .dto.chat_dto import ChatTurnDTO

chat_router = APIRouter(tags=["chat"])


async def _as_sse_events(envelopes: AsyncIterator[dict[str, Any]]) -> AsyncIterator[dict[str, str]]:
    """Wrap gMART-style envelopes into the dict shape sse_starlette expects (event/data)."""

    async for envelope in envelopes:
        yield {"event": envelope.get("type", "message"), "data": json.dumps(envelope, ensure_ascii=False)}


@chat_router.post("/scenarios/{scenario_id}/chat/stream")
async def chat_stream(
    scenario_id: int,
    request: Request,
    params: ChatTurnDTO,
    token: str = Depends(verify_bearer_token),
    config: Config = Depends(get_config),
) -> EventSourceResponse:
    """
    Run one turn of the GenPlanner chat agent over SSE. Bearer required (forwarded to
    Urban API and the generation call, same as the plain REST endpoints); project_id and
    the choice of prod/test Urban API stay outside chat text -- project_id is resolved
    from scenario_id, `test` comes from the request body like on GenPlannerFuncZonesDTO.
    """

    genplanner_service: GenPlannerService = get_genplanner_service(request, params.test)
    llm_client = get_llm_chat_client(request)
    if llm_client is None:
        raise http_exception(
            503,
            "Chat feature is not configured",
            _input={"scenario_id": scenario_id},
            _detail={"reason": "VLLM_BASE_URL/CHAT_MODEL is not set"},
        )

    chat_storage_client = get_chat_storage_client(request)
    user_id = extract_user_id(token)

    envelopes = stream_chat_turn(
        llm_client=llm_client,
        chat_storage_client=chat_storage_client,
        genplanner_service=genplanner_service,
        config=config,
        token=token,
        user_id=user_id,
        scenario_id=scenario_id,
        params=params,
    )
    return EventSourceResponse(_as_sse_events(envelopes))
