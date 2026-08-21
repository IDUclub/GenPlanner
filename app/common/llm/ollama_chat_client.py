import json
from typing import Any, AsyncIterator

import aiohttp
from iduconfig import Config
from loguru import logger

from app.common.config_utils import get_optional_config
from app.common.llm.chat_client import LLMChatError, loads_json_object


class OllamaChatError(LLMChatError):
    """Raised when Ollama's /api/chat returns a non-2xx response or a malformed stream."""


class OllamaChatClient:
    """
    Thin async wrapper around Ollama's `/api/chat` endpoint.

    Uses aiohttp rather than httpx to stay consistent with the rest of this codebase
    (see AsyncJsonApiHandler) instead of adding a second HTTP library. A new
    aiohttp.ClientSession is opened per call, matching AsyncJsonApiHandler.get().

    Attributes:
        base_url (str): Ollama server base URL (e.g. http://ollama-host:11434).
        default_model (str): Model used when a call doesn't override it.
    """

    def __init__(self, base_url: str, default_model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        request_timeout_seconds: float = 900.0,
    ) -> AsyncIterator[str]:
        """
        Stream assistant content deltas from `/api/chat` (stream=True).

        Args:
            messages: Chat messages in Ollama's `{"role": ..., "content": ...}` shape.
            model: Overrides `default_model` for this call.
            temperature: Sampling temperature, passed through as `options.temperature`.
            request_timeout_seconds: Total aiohttp timeout for the whole stream.

        Yields:
            str: Each incremental piece of `message.content` as it arrives.

        Raises:
            OllamaChatError: Non-2xx response, an `error` field in a stream chunk, or a
                connection failure.
        """

        payload: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": messages,
            "stream": True,
        }
        if temperature is not None:
            payload["options"] = {"temperature": temperature}

        timeout = aiohttp.ClientTimeout(total=request_timeout_seconds)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(f"{self.base_url}/api/chat", json=payload) as response:
                    if response.status != 200:
                        body = await response.text()
                        raise OllamaChatError(f"Ollama /api/chat returned {response.status}: {body[:500]}")

                    async for raw_line in response.content:
                        line = raw_line.strip()
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            logger.warning(f"Skipping malformed Ollama stream line: {line[:200]!r}")
                            continue

                        if chunk.get("error"):
                            raise OllamaChatError(str(chunk["error"]))

                        delta = (chunk.get("message") or {}).get("content")
                        if delta:
                            yield delta

                        if chunk.get("done"):
                            break
        except aiohttp.ClientError as exc:
            raise OllamaChatError(f"Ollama /api/chat request failed: {exc}") from exc

    async def complete_json(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        *,
        model: str | None = None,
        temperature: float | None = None,
        request_timeout_seconds: float = 120.0,
    ) -> dict[str, Any]:
        """
        Non-streaming structured-output call.

        Constrains generation to `schema` (a JSON Schema object, passed as Ollama's
        `format` field) and returns the parsed JSON object -- used for the chat agent's
        one-call-per-turn decision step instead of hand-rolled tool-calling, which is
        unreliable across the small local models Ollama typically serves.

        Args:
            messages: Chat messages, system prompt included.
            schema: JSON Schema the response must conform to.
            model: Overrides `default_model` for this call.
            temperature: Sampling temperature, passed through as `options.temperature`.
            request_timeout_seconds: aiohttp timeout for the call.

        Returns:
            dict[str, Any]: The parsed JSON object from `message.content`.

        Raises:
            OllamaChatError: Non-2xx response, empty content, or content that isn't
                (or doesn't contain) a valid JSON object.
        """

        payload: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": messages,
            "stream": False,
            "format": schema,
        }
        if temperature is not None:
            payload["options"] = {"temperature": temperature}

        timeout = aiohttp.ClientTimeout(total=request_timeout_seconds)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(f"{self.base_url}/api/chat", json=payload) as response:
                    if response.status != 200:
                        body = await response.text()
                        raise OllamaChatError(f"Ollama /api/chat returned {response.status}: {body[:500]}")
                    data = await response.json()
        except aiohttp.ClientError as exc:
            raise OllamaChatError(f"Ollama /api/chat request failed: {exc}") from exc

        content = (data.get("message") or {}).get("content")
        if not content:
            raise OllamaChatError(f"Ollama returned no message content: {data!r}")

        return loads_json_object(content)


def build_ollama_chat_client(config: Config) -> "OllamaChatClient | None":
    """
    Build the Ollama chat client, kept as an alternative backend selected by
    LLM_PROVIDER=ollama. Returns None if OLLAMA_BASE_URL isn't configured, so the chat
    feature can be left disabled by simply leaving it empty.
    """

    base_url = get_optional_config(config, "OLLAMA_BASE_URL")
    if not base_url:
        return None

    default_model = get_optional_config(config, "CHAT_MODEL") or get_optional_config(config, "GENERATE_MODEL")
    if not default_model:
        return None

    return OllamaChatClient(base_url, default_model)
