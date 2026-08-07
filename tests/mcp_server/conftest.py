from unittest.mock import MagicMock

import aiohttp
import pytest


class FakeResponse:
    """Stands in for aiohttp.ClientResponse's async context manager protocol."""

    def __init__(self, status: int, json_body=None, text_body: str | None = None, bad_content_type: bool = False):
        self.status = status
        self._json_body = json_body
        self._text_body = text_body
        self._bad_content_type = bad_content_type

    async def json(self):
        if self._bad_content_type:
            raise aiohttp.ContentTypeError(None, ())
        return self._json_body

    async def text(self):
        return self._text_body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class FakeSession:
    """Stands in for aiohttp.ClientSession's async context manager protocol."""

    def __init__(self, response: FakeResponse):
        self.response = response
        self.request_calls: list[dict] = []

    def request(self, method, url, *, params=None, json=None, headers=None):
        self.request_calls.append({"method": method, "url": url, "params": params, "json": json, "headers": headers})
        return self.response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


@pytest.fixture
def patch_client_session(monkeypatch):
    """
    Patches aiohttp.ClientSession as used by app.mcp_server.api_client, returning the
    FakeSession so tests can assert on the request made and control the response.
    """

    def _patch(response: FakeResponse) -> FakeSession:
        session = FakeSession(response)
        monkeypatch.setattr("aiohttp.ClientSession", MagicMock(return_value=session))
        return session

    return _patch
