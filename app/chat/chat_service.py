from typing import Any, AsyncIterator

from fastapi import HTTPException
from iduconfig import Config
from loguru import logger

from app.common.chat_storage.chat_storage_client import ChatStorageClient, ChatStorageError
from app.common.exceptions.http_exception import http_exception
from app.common.llm.ollama_chat_client import OllamaChatClient, OllamaChatError
from app.gen_planner.dto.gen_planner_func_dto import GenPlannerFuncZonesDTO
from app.gen_planner.gen_planner_service import GenPlannerService

from .agent.draft import GenerationDraft
from .agent.prompts import build_system_prompt
from .agent.schema import AGENT_ACTION_SCHEMA
from .dto.chat_dto import ChatTurnDTO

_CHUNK_SIZE = 24


def _chunk_reply(reply: str) -> list[str]:
    """
    Split an already-generated reply into small pieces so it can be streamed to the
    frontend like a token-by-token response, without a second LLM call just for
    streaming -- the decision step already produced the final text.
    """

    if not reply:
        return []
    return [reply[i : i + _CHUNK_SIZE] for i in range(0, len(reply), _CHUNK_SIZE)]


def _extract_draft_from_history(messages: list[dict[str, Any]]) -> GenerationDraft:
    """Find the most recent assistant message carrying a `draft` in its metadata."""

    for message in reversed(messages):
        if message.get("role") != "assistant":
            continue
        draft_data = (message.get("metadata") or {}).get("draft")
        if draft_data:
            return GenerationDraft.model_validate(draft_data)
    return GenerationDraft()


def _build_llm_history(messages: list[dict[str, Any]], max_messages: int = 10) -> list[dict[str, str]]:
    """
    Compact ChatStorage messages into plain user/assistant turns for the LLM.

    ChatStorage's MessageSchema always returns text as `parts[*].payload.text` (kind
    "text") -- there is no top-level `content` string on the response, even though the
    create-message request DTO accepts one for convenience. A plain `content` is still
    checked first defensively in case of a future/alternate response shape.
    """

    result: list[dict[str, str]] = []
    for message in messages:
        role = message.get("role")
        if role not in ("user", "assistant"):
            continue

        content = message.get("content")
        if isinstance(content, str) and content.strip():
            result.append({"role": role, "content": content.strip()})
            continue

        texts = [
            part["payload"]["text"]
            for part in (message.get("parts") or [])
            if part.get("kind") == "text" and (part.get("payload") or {}).get("text")
        ]
        combined = "\n".join(texts).strip()
        if combined:
            result.append({"role": role, "content": combined})

    return result[-max_messages:]


async def _resolve_project_id(genplanner_service: GenPlannerService, scenario_id: int, token: str) -> int:
    """
    Resolve project_id from scenario_id, same lookup GenPlannerService.restore_params
    does -- needed here because GenPlannerFuncZonesDTO requires project_id at
    construction time (pydantic), and the chat flow only ever has scenario_id.
    """

    scenario_info = await genplanner_service.urban_api_client.get_scenario_info(scenario_id, token)
    project_id = (scenario_info.get("project") or {}).get("project_id")
    if project_id is None:
        raise http_exception(
            404,
            "Project ID cannot be resolved from scenario info",
            _input={"scenario_id": scenario_id},
            _detail={"scenario_info": scenario_info},
        )
    return project_id


async def stream_chat_turn(
    *,
    ollama_client: OllamaChatClient,
    chat_storage_client: ChatStorageClient | None,
    genplanner_service: GenPlannerService,
    config: Config,
    token: str,
    user_id: str | None,
    scenario_id: int,
    params: ChatTurnDTO,
) -> AsyncIterator[dict[str, Any]]:
    """
    Run one turn of the GenPlanner chat agent, yielding gMART-style envelopes:
    `chat_created`, `token`, `result`, `warning`, `error`, `done`. Transport-agnostic --
    the controller wraps each envelope into an SSE event.

    One `complete_json` call per turn decides the action (see agent/schema.py) and
    produces the reply text in the same call; the reply is then chunked and "replayed"
    as `token` events rather than issuing a second LLM call just for streaming.
    """

    chat_id = params.chat_id
    persist = chat_storage_client is not None and bool(user_id)

    history: list[dict[str, str]] = []
    draft = GenerationDraft()

    if persist and chat_id:
        try:
            existing = await chat_storage_client.get_chat(user_id, chat_id)
            messages = existing.get("messages") or []
            history = _build_llm_history(messages)
            draft = _extract_draft_from_history(messages)
        except ChatStorageError as exc:
            logger.warning(f"chat_storage get_chat (history) failed: {exc}")
            yield {
                "type": "warning",
                "stage": "load_history",
                "detail": str(exc),
                "message": "Не удалось загрузить историю чата — отвечаю без учёта предыдущих сообщений.",
            }

    if persist and not chat_id:
        try:
            created = await chat_storage_client.create_chat(user_id, scenario_id=scenario_id)
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
            await chat_storage_client.add_message(user_id, chat_id, role="user", content=params.user_query)
        except ChatStorageError as exc:
            logger.warning(f"chat_storage add user message failed: {exc}")
            yield {
                "type": "warning",
                "stage": "add_user_message",
                "detail": str(exc),
                "message": "Ответ сформирован, но не сохранён в историю чата (сервис истории недоступен).",
            }

    system_prompt = build_system_prompt(draft)
    llm_messages = [
        {"role": "system", "content": system_prompt},
        *history,
        {"role": "user", "content": params.user_query},
    ]

    try:
        decision = await ollama_client.complete_json(llm_messages, schema=AGENT_ACTION_SCHEMA)
    except OllamaChatError as exc:
        logger.warning(f"chat agent decision failed: {exc}")
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
            reply = (
                reply or "Нужен хотя бы примерный баланс зон, прежде чем запускать генерацию — какие пропорции хочешь?"
            )
        else:
            try:
                project_id = await _resolve_project_id(genplanner_service, scenario_id, token)
                dto = GenPlannerFuncZonesDTO(
                    project_id=project_id,
                    scenario_id=scenario_id,
                    territory_balance=draft.territory_balance,
                    neighbour_pairs=draft.neighbour_pairs,
                    forbidden_pairs=draft.forbidden_pairs,
                    min_block_area=draft.min_block_area or {},
                    elevation_angle=draft.elevation_angle,
                    roads_extend_distance=draft.roads_extend_distance,
                    test=params.test,
                )
                result = await genplanner_service.run_func_generation(dto, token, config)
                result_payload = result.model_dump()
            except HTTPException as exc:
                detail = exc.detail if isinstance(exc.detail, dict) else {"msg": str(exc.detail)}
                logger.warning(f"chat-triggered generation failed: {detail}")
                yield {"type": "warning", "stage": "run_generation", "detail": detail}
                reply = reply or (
                    "Генерация не запустилась: "
                    f"{detail.get('msg', 'ошибка валидации параметров')}. Уточни, что поправить, и попробуем снова."
                )

    for piece in _chunk_reply(reply):
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
