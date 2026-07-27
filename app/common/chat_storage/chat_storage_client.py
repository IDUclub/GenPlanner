from typing import Any

import aiohttp
from idu_service_auth import KeycloakTokenClient
from iduconfig import Config

from app.common.config_utils import get_optional_config


class ChatStorageError(Exception):
    """Raised when ChatStorage returns a non-2xx response."""

    def __init__(self, status: int, body: Any) -> None:
        super().__init__(f"ChatStorage returned {status}: {body}")
        self.status = status
        self.body = body


class ChatStorageClient:
    """
    Async wrapper around the IDUclub ChatStorage service, used to persist chat history
    for the GenPlanner chat feature.

    Mirrors UrbanApiClient's styling: instantiated fresh per request, aiohttp-based, no
    persistent session held between calls. Authenticated with OUR service account's
    Keycloak token (client_credentials, via `idu_service_auth.KeycloakTokenClient`)
    rather than the end user's token, since chat turns can outlive a short-lived user
    token; the end user is identified to ChatStorage via the `X-User-Id` header (required
    when authenticating with a service token, per ChatStorage's own OpenAPI docs).

    Endpoint paths/payload shapes confirmed against the real deployed instance's
    /openapi.json ("IDU LLM Chat History"): `create_chat` -> `MessageSchema`/`ChatSchema`
    responses carry messages as `parts` (kind/payload), never a top-level `content` string,
    even though the request DTO accepts a plain `content` for convenience.

    Attributes:
        base_url (str): ChatStorage base URL.
        token_client (KeycloakTokenClient): Provides the service's Bearer token.
        timeout_seconds (float): aiohttp timeout for all calls.
    """

    def __init__(
        self,
        base_url: str,
        token_client: KeycloakTokenClient,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token_client = token_client
        self.timeout_seconds = timeout_seconds

    async def _headers(self, user_id: str) -> dict[str, str]:
        headers = await self.token_client.get_authorization_headers()
        headers["X-User-Id"] = user_id
        return headers

    async def _request(self, method: str, url: str, user_id: str, json_body: dict[str, Any] | None) -> dict[str, Any]:
        headers = await self._headers(user_id)
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(method, url, json=json_body, headers=headers) as response:
                if response.status not in (200, 201):
                    try:
                        body = await response.json()
                    except aiohttp.ContentTypeError:
                        body = await response.text()
                    raise ChatStorageError(response.status, body)
                return await response.json()

    async def create_chat(
        self,
        user_id: str,
        *,
        title: str | None = None,
        scenario_id: int | str | None = None,
        project_id: int | str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Create a new chat owned by `user_id`.

        Returns:
            dict[str, Any]: At least `{"chat_id": ..., "title": ...}`.
        """

        body: dict[str, Any] = {
            "title": title,
            "scenario_id": scenario_id,
            "project_id": project_id,
        }
        if metadata is not None:
            body["metadata"] = metadata
        return await self._request("POST", f"{self.base_url}/api/v1/chat_history/create_chat", user_id, body)

    async def add_message(
        self,
        user_id: str,
        chat_id: str,
        *,
        role: str,
        content: str | None = None,
        parts: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Append a message to `chat_id`. Either `content` (plain text) or `parts`
        (structured multi-part payload, e.g. text + geo-layer file parts) must be given.

        Returns:
            dict[str, Any]: At least `{"message_id": ...}`.
        """

        body: dict[str, Any] = {"role": role}
        if metadata is not None:
            body["metadata"] = metadata
        if parts is not None:
            body["parts"] = parts
        else:
            body["content"] = content
        return await self._request("POST", f"{self.base_url}/api/v1/chat_history/{chat_id}/message", user_id, body)

    async def get_chat(self, user_id: str, chat_id: str) -> dict[str, Any]:
        """
        Fetch a chat's full history.

        Returns:
            dict[str, Any]: At least `{"chat_id": ..., "messages": [...]}`.
        """

        return await self._request("GET", f"{self.base_url}/api/v1/chat_history/{chat_id}", user_id, None)


def build_chat_storage_client(config: Config, token_client: KeycloakTokenClient | None) -> "ChatStorageClient | None":
    """
    Build the ChatStorage client used to persist chat history. Returns None if
    CHAT_STORAGE_BASE_URL isn't configured or the Keycloak service token client
    couldn't be built (ChatStorage auth depends on it) -- chat still works, it's just
    not saved.
    """

    base_url = get_optional_config(config, "CHAT_STORAGE_BASE_URL")
    if not base_url or token_client is None:
        return None

    timeout_raw = get_optional_config(config, "CHAT_STORAGE_TIMEOUT_SECONDS")
    timeout_seconds = float(timeout_raw) if timeout_raw else 10.0

    return ChatStorageClient(base_url, token_client, timeout_seconds=timeout_seconds)
