from typing import Any

import aiohttp


class GenPlannerApiError(Exception):
    """Raised when the GenPlanner REST API returns a non-2xx response."""

    def __init__(self, status: int, body: Any) -> None:
        super().__init__(f"GenPlanner API returned {status}: {body}")
        self.status = status
        self.body = body


def _stringify_query_params(params: dict[str, Any] | None) -> dict[str, Any] | None:
    """
    aiohttp's `params=` only accepts str/int/float; bool must be stringified first
    (FastAPI/Starlette parse "true"/"false" query values as bool on the other end).
    """

    if params is None:
        return None
    return {key: (str(value).lower() if isinstance(value, bool) else value) for key, value in params.items()}


class GenPlannerApiClient:
    """
    Thin async client for the GenPlanner API used by the MCP server, mirroring
    ChatStorageClient/VllmChatClient's style (aiohttp, one ClientSession per call).

    Unlike AsyncJsonApiHandler this also supports POST with both query params and a
    JSON body, since run_func_generation splits GenPlannerFuncZonesDTO fields across
    both.
    """

    def __init__(self, base_url: str, timeout_seconds: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def _request(
        self,
        method: str,
        extra_url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        url = f"{self.base_url}{extra_url}"
        params = _stringify_query_params(params)
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(method, url, params=params, json=json_body, headers=headers) as response:
                if response.status not in (200, 201):
                    try:
                        body = await response.json()
                    except aiohttp.ContentTypeError:
                        body = await response.text()
                    raise GenPlannerApiError(response.status, body)
                return await response.json()

    async def get(self, extra_url: str, *, params: dict[str, Any] | None = None) -> Any:
        return await self._request("GET", extra_url, params=params)

    async def post(
        self,
        extra_url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        return await self._request("POST", extra_url, params=params, json_body=json_body, headers=headers)
