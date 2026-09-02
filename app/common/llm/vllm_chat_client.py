import json
from typing import Any, AsyncIterator

import aiohttp
from iduconfig import Config
from loguru import logger

from app.common.config_utils import get_optional_config
from app.common.llm.chat_client import LLMChatError, loads_json_object

_SSE_DATA_PREFIX = "data:"
_SSE_DONE = "[DONE]"
_JSON_SCHEMA_NAME = "response"


class VllmChatError(LLMChatError):
    """Raised when vLLM's /v1/chat/completions returns a non-2xx response or a malformed stream."""


def _normalize_base_url(base_url: str) -> str:
    """
    vLLM serves the OpenAI-compatible API under `/v1`, and operators configure the base
    URL both with and without that suffix -- strip it so request paths never double it.
    """

    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        normalized = normalized[: -len("/v1")]
    return normalized


class VllmChatClient:
    """
    Thin async wrapper around vLLM's OpenAI-compatible `/v1/chat/completions` endpoint.

    Uses aiohttp rather than httpx or the openai SDK to stay consistent with the rest of
    this codebase (see AsyncJsonApiHandler) instead of adding another HTTP dependency. A
    new aiohttp.ClientSession is opened per call, matching AsyncJsonApiHandler.get().

    Attributes:
        base_url (str): vLLM server base URL without the `/v1` suffix
            (e.g. http://a6k4.dgx:8001).
        default_model (str): Model used when a call doesn't override it.
    """

    def __init__(self, base_url: str, default_model: str) -> None:
        self.base_url = _normalize_base_url(base_url)
        self.default_model = default_model

    @property
    def _chat_completions_url(self) -> str:
        return f"{self.base_url}/v1/chat/completions"

    @staticmethod
    def _raise_on_payload_error(chunk: dict[str, Any]) -> None:
        error = chunk.get("error")
        if error:
            raise VllmChatError(str(error))

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        request_timeout_seconds: float = 900.0,
    ) -> AsyncIterator[str]:
        """
        Stream assistant content deltas from `/v1/chat/completions` (stream=True).

        Args:
            messages: Chat messages in `{"role": ..., "content": ...}` shape.
            model: Overrides `default_model` for this call.
            temperature: Sampling temperature.
            request_timeout_seconds: Total aiohttp timeout for the whole stream.

        Yields:
            str: Each incremental piece of `choices[0].delta.content` as it arrives.
                Reasoning deltas (`reasoning_content`, emitted by reasoning models such as
                gpt-oss) are skipped -- only user-facing content is streamed.

        Raises:
            VllmChatError: Non-2xx response, an `error` field in a stream chunk, or a
                connection failure.
        """

        payload: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": messages,
            "stream": True,
        }
        if temperature is not None:
            payload["temperature"] = temperature

        timeout = aiohttp.ClientTimeout(total=request_timeout_seconds)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self._chat_completions_url, json=payload) as response:
                    if response.status != 200:
                        body = await response.text()
                        raise VllmChatError(f"vLLM /v1/chat/completions returned {response.status}: {body[:500]}")

                    async for raw_line in response.content:
                        line = raw_line.decode("utf-8", errors="replace").strip()
                        if not line or not line.startswith(_SSE_DATA_PREFIX):
                            continue

                        data = line[len(_SSE_DATA_PREFIX) :].strip()
                        if data == _SSE_DONE:
                            break

                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            logger.warning(f"Skipping malformed vLLM stream line: {data[:200]!r}")
                            continue

                        self._raise_on_payload_error(chunk)

                        choices = chunk.get("choices") or []
                        if not choices:
                            continue

                        delta = (choices[0].get("delta") or {}).get("content")
                        if delta:
                            yield delta
        except aiohttp.ClientError as exc:
            raise VllmChatError(f"vLLM /v1/chat/completions request failed: {exc}") from exc

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

        Constrains generation to `schema` through OpenAI-style
        `response_format={"type": "json_schema", ...}`, which vLLM implements with guided
        decoding -- used for the chat agent's one-call-per-turn decision step instead of
        hand-rolled tool-calling, which is unreliable across small local models.

        Args:
            messages: Chat messages, system prompt included.
            schema: JSON Schema the response must conform to.
            model: Overrides `default_model` for this call.
            temperature: Sampling temperature.
            request_timeout_seconds: aiohttp timeout for the call.

        Returns:
            dict[str, Any]: The parsed JSON object from `choices[0].message.content`.

        Raises:
            VllmChatError: Non-2xx response, empty content, or content that isn't
                (or doesn't contain) a valid JSON object.
        """

        payload: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": messages,
            "stream": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": _JSON_SCHEMA_NAME, "schema": schema},
            },
        }
        if temperature is not None:
            payload["temperature"] = temperature

        timeout = aiohttp.ClientTimeout(total=request_timeout_seconds)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self._chat_completions_url, json=payload) as response:
                    if response.status != 200:
                        body = await response.text()
                        raise VllmChatError(f"vLLM /v1/chat/completions returned {response.status}: {body[:500]}")
                    data = await response.json()
        except aiohttp.ClientError as exc:
            raise VllmChatError(f"vLLM /v1/chat/completions request failed: {exc}") from exc

        self._raise_on_payload_error(data)

        choices = data.get("choices") or []
        content = (choices[0].get("message") or {}).get("content") if choices else None
        if not content:
            raise VllmChatError(f"vLLM returned no message content: {data!r}")

        return loads_json_object(content)


def build_vllm_chat_client(config: Config) -> "VllmChatClient | None":
    """
    Build the vLLM chat client used by the GenPlanner chat agent. Returns None if
    VLLM_BASE_URL or the model name isn't configured, so the chat feature can be left
    disabled by simply leaving them empty.
    """

    base_url = get_optional_config(config, "VLLM_BASE_URL")
    if not base_url:
        return None

    default_model = get_optional_config(config, "CHAT_MODEL") or get_optional_config(config, "GENERATE_MODEL")
    if not default_model:
        return None

    return VllmChatClient(base_url, default_model)
