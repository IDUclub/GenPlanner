import json
from typing import Any, AsyncIterator, Protocol


class LLMChatError(Exception):
    """Base error for every chat-completions backend, so callers catch one type."""


class ChatClient(Protocol):
    """Provider-agnostic chat interface implemented by VllmChatClient and OllamaChatClient."""

    base_url: str
    default_model: str

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        request_timeout_seconds: float = 900.0,
    ) -> AsyncIterator[str]: ...

    async def complete_json(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        *,
        model: str | None = None,
        temperature: float | None = None,
        request_timeout_seconds: float = 120.0,
    ) -> dict[str, Any]: ...


def loads_json_object(text: str) -> dict[str, Any]:
    """
    Parse a JSON object out of model output, tolerating formatting artifacts -- some
    models wrap structured output in chain-of-thought text or code fences even when a
    schema was requested. Tries a strict parse first, then falls back to the outermost
    `{...}` span.
    """

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise LLMChatError(f"Model output is not a JSON object: {text[:500]!r}")

    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LLMChatError(f"Model output is not a JSON object: {text[:500]!r}") from exc
