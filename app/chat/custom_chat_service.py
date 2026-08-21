import json
from typing import Any, AsyncIterator

from fastapi import HTTPException
from loguru import logger

from app.common.chat_storage.chat_storage_client import ChatStorageClient, ChatStorageError
from app.common.geometries_dto.geometries import PolygonalFeatureCollection
from app.common.llm.chat_client import ChatClient, LLMChatError
from app.gen_planner.dto.gen_planner_custom_dto import GenPlannerCustomDTO
from app.gen_planner.gen_planner_service import GenPlannerService

from .agent.custom_draft import CustomGenerationDraft
from .agent.custom_prompts import build_custom_system_prompt
from .agent.custom_schema import CUSTOM_AGENT_ACTION_SCHEMA
from .chat_common import build_llm_history, chunk_reply
from .dto.chat_custom_dto import ChatCustomTurnDTO


def _extract_custom_draft_from_history(messages: list[dict[str, Any]]) -> CustomGenerationDraft:
    """Find the most recent assistant message carrying a `draft` in its metadata."""

    for message in reversed(messages):
        if message.get("role") != "assistant":
            continue
        draft_data = (message.get("metadata") or {}).get("draft")
        if draft_data:
            return CustomGenerationDraft.model_validate(draft_data)
    return CustomGenerationDraft()


def _territory_to_geojson_dict(territory: PolygonalFeatureCollection) -> dict[str, Any]:
    """
    Serialize via geopandas rather than PolygonalFeatureCollection.as_dict(): as_dict()
    omits the per-feature GeoJSON `type` key (it's only ever fed back into
    gpd.GeoDataFrame.from_features, which doesn't need it), so it doesn't round-trip
    through PolygonalFeatureCollection.model_validate() the way this needs to.
    """

    return json.loads(territory.as_gdf(4326).to_json())


def _extract_territory_from_history(messages: list[dict[str, Any]]) -> PolygonalFeatureCollection | None:
    """
    Find the most recent user message carrying a `territory` in its metadata -- the
    boundary uploaded on some earlier turn of this chat, so later turns don't need to
    re-upload the file unless they want to replace it. Most recent (not earliest) so a
    mid-conversation re-upload actually overrides the original boundary for turns after it.
    """

    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        territory_data = (message.get("metadata") or {}).get("territory")
        if territory_data:
            return PolygonalFeatureCollection.model_validate(territory_data)
    return None


async def stream_custom_chat_turn(
    *,
    llm_client: ChatClient,
    chat_storage_client: ChatStorageClient | None,
    genplanner_service: GenPlannerService,
    user_id: str | None,
    territory: PolygonalFeatureCollection | None,
    params: ChatCustomTurnDTO,
) -> AsyncIterator[dict[str, Any]]:
    """
    Run one turn of the GenPlanner custom-territory chat agent (no scenario_id/project_id
    -- the territory is an uploaded file boundary), yielding gMART-style envelopes:
    `chat_created`, `token`, `result`, `warning`, `error`, `done`.

    Unlike stream_chat_turn, there's no Urban API scenario to resolve project_id, roads,
    water or slope exclusion from -- generation runs on the uploaded territory geometry
    alone, applying a single zoning profile (see CustomGenerationDraft).
    """

    chat_id = params.chat_id
    persist = chat_storage_client is not None and bool(user_id)

    history: list[dict[str, str]] = []
    draft = CustomGenerationDraft()
    territory_from_history: PolygonalFeatureCollection | None = None

    if persist and chat_id:
        try:
            existing = await chat_storage_client.get_chat(user_id, chat_id)
            messages = existing.get("messages") or []
            history = build_llm_history(messages)
            draft = _extract_custom_draft_from_history(messages)
            territory_from_history = _extract_territory_from_history(messages)
        except ChatStorageError as exc:
            logger.warning(f"chat_storage get_chat (history) failed: {exc}")
            yield {
                "type": "warning",
                "stage": "load_history",
                "detail": str(exc),
                "message": "Не удалось загрузить историю чата — отвечаю без учёта предыдущих сообщений.",
            }

    resolved_territory = territory or territory_from_history
    if resolved_territory is None:
        yield {
            "type": "error",
            "stage": "territory",
            "detail": "territory_file is required on the first message of a custom chat",
        }
        yield {"type": "done", "chat_id": chat_id, "assistant_message_id": None}
        return

    is_new_territory_upload = territory is not None

    if persist and not chat_id:
        try:
            created = await chat_storage_client.create_chat(user_id, scenario_id=None)
            chat_id = created.get("chat_id")
            yield {"type": "chat_created", "chat_id": chat_id, "title": created.get("title")}
        except ChatStorageError as exc:
            logger.warning(f"chat_storage create_chat failed: {exc}")
            yield {
                "type": "warning",
                "stage": "create_chat",
                "detail": str(exc),
                "message": "Ответ сформирован, но не сохранён в историю чата (сервис истории недоступен).",
            }
            persist = False

    if persist and chat_id:
        try:
            user_message_metadata = (
                {"territory": _territory_to_geojson_dict(resolved_territory)} if is_new_territory_upload else None
            )
            await chat_storage_client.add_message(
                user_id, chat_id, role="user", content=params.user_query, metadata=user_message_metadata
            )
        except ChatStorageError as exc:
            logger.warning(f"chat_storage add user message failed: {exc}")
            yield {
                "type": "warning",
                "stage": "add_user_message",
                "detail": str(exc),
                "message": "Ответ сформирован, но не сохранён в историю чата (сервис истории недоступен).",
            }

    system_prompt = build_custom_system_prompt(draft)
    llm_messages = [
        {"role": "system", "content": system_prompt},
        *history,
        {"role": "user", "content": params.user_query},
    ]

    try:
        decision = await llm_client.complete_json(llm_messages, schema=CUSTOM_AGENT_ACTION_SCHEMA)
    except LLMChatError as exc:
        logger.warning(f"custom chat agent decision failed: {exc}")
        yield {"type": "error", "stage": "llm", "detail": str(exc)}
        yield {"type": "done", "chat_id": chat_id, "assistant_message_id": None}
        return

    action = decision.get("action") or "chat"
    reply = decision.get("reply") or ""
    patch = decision.get("patch") or {}

    if patch:
        draft = draft.merge_patch(patch)

    result_payload: dict[str, Any] | None = None

    if action == "run_generation":
        if not draft.is_ready_for_generation():
            reply = reply or "Нужен выбранный профиль зонирования, прежде чем запускать генерацию — какой хочешь?"
        else:
            assert draft.profile_id is not None
            try:
                dto = GenPlannerCustomDTO(profile_id=draft.profile_id, territory=resolved_territory)
                result = await genplanner_service.run_custom_func_generation(dto)
                result_payload = result.model_dump()
            except HTTPException as exc:
                detail = exc.detail if isinstance(exc.detail, dict) else {"msg": str(exc.detail)}
                logger.warning(f"custom chat-triggered generation failed: {detail}")
                yield {"type": "warning", "stage": "run_generation", "detail": detail}
                reply = reply or (
                    "Генерация не запустилась: "
                    f"{detail.get('msg', 'ошибка валидации параметров')}. Уточни, что поправить, и попробуем снова."
                )

    for piece in chunk_reply(reply):
        yield {"type": "token", "content": piece}

    if result_payload is not None:
        yield {"type": "result", "zones": result_payload["zones"], "roads": result_payload["roads"]}

    assistant_message_id = None
    if persist and chat_id:
        try:
            stored = await chat_storage_client.add_message(
                user_id,
                chat_id,
                role="assistant",
                content=reply,
                metadata={"draft": draft.model_dump(exclude_none=True), "action": action},
            )
            assistant_message_id = stored.get("message_id")
        except ChatStorageError as exc:
            logger.warning(f"chat_storage add assistant message failed: {exc}")
            yield {
                "type": "warning",
                "stage": "add_assistant_message",
                "detail": str(exc),
                "message": "Ответ сформирован, но не сохранён в историю чата (сервис истории недоступен).",
            }

    yield {"type": "done", "chat_id": chat_id, "assistant_message_id": assistant_message_id}
