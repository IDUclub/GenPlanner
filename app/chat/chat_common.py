from typing import Any

from loguru import logger

from app.common.chat_storage.chat_storage_client import ChatStorageClient, ChatStorageError

_CHUNK_SIZE = 24


def chunk_reply(reply: str) -> list[str]:
    """
    Split an already-generated reply into small pieces so it can be streamed to the
    frontend like a token-by-token response, without a second LLM call just for
    streaming -- the decision step already produced the final text.
    """

    if not reply:
        return []
    return [reply[i : i + _CHUNK_SIZE] for i in range(0, len(reply), _CHUNK_SIZE)]


def build_llm_history(messages: list[dict[str, Any]], max_messages: int = 10) -> list[dict[str, str]]:
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


async def persist_user_turn(
    chat_storage_client: ChatStorageClient,
    user_id: str,
    chat_id: str | None,
    *,
    scenario_id: int | None,
    user_query: str,
    title: str,
    user_message_metadata: dict[str, Any] | None = None,
) -> tuple[str | None, list[dict[str, Any]]]:
    """
    Create the chat when it is new and append the user's message to it.

    Runs after the model has answered, not before, so a brand-new chat can be created
    with the title the model produced in the same call. Returns the chat id (None when
    creation failed, meaning nothing can be persisted for this turn) together with the
    envelopes the caller has to yield -- a plain function rather than a generator so the
    caller can act on the chat id instead of having to sift it back out of the stream.
    """

    envelopes: list[dict[str, Any]] = []

    if not chat_id:
        try:
            created = await chat_storage_client.create_chat(user_id, title=title, scenario_id=scenario_id)
            chat_id = created.get("chat_id")
            envelopes.append({"type": "chat_created", "chat_id": chat_id, "title": created.get("title")})
        except ChatStorageError as exc:
            logger.warning(f"chat_storage create_chat failed: {exc}")
            envelopes.append(
                {
                    "type": "warning",
                    "stage": "create_chat",
                    "detail": str(exc),
                    "message": "Ответ сформирован, но не сохранён в историю чата (сервис истории недоступен).",
                }
            )
            return None, envelopes

    try:
        await chat_storage_client.add_message(
            user_id, chat_id, role="user", content=user_query, metadata=user_message_metadata
        )
    except ChatStorageError as exc:
        logger.warning(f"chat_storage add user message failed: {exc}")
        envelopes.append(
            {
                "type": "warning",
                "stage": "add_user_message",
                "detail": str(exc),
                "message": "Ответ сформирован, но не сохранён в историю чата (сервис истории недоступен).",
            }
        )

    return chat_id, envelopes
