from typing import Any

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
