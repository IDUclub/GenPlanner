from unittest.mock import MagicMock

import pytest


class FakeStreamContent:
    """Stands in for aiohttp.ClientResponse.content, which yields raw bytes lines."""

    def __init__(self, lines: list[bytes]):
        self._lines = lines

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for line in self._lines:
            yield line


class FakeResponse:
    """Stands in for aiohttp.ClientResponse's async context manager protocol."""

    def __init__(
        self,
        status: int,
        json_body=None,
        text_body: str | None = None,
        stream_lines: list[bytes] | None = None,
    ):
        self.status = status
        self.content = FakeStreamContent(stream_lines or [])
        self._json_body = json_body
        self._text_body = text_body

    async def json(self):
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
        self.post_calls: list[dict] = []

    def post(self, url, *, json=None):
        self.post_calls.append({"url": url, "json": json})
        return self.response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


@pytest.fixture
def patch_client_session(monkeypatch):
    """
    Patches aiohttp.ClientSession as used by the chat clients, returning the FakeSession
    so tests can assert on the request made and control the response.
    """

    def _patch(response: FakeResponse) -> FakeSession:
        session = FakeSession(response)
        monkeypatch.setattr("aiohttp.ClientSession", MagicMock(return_value=session))
        return session

    return _patch


class FakeConfig:
    """Stands in for iduconfig.Config, which raises ValueError for missing/empty keys."""

    def __init__(self, values: dict[str, str]):
        self._values = values

    def get(self, key: str) -> str:
        value = self._values.get(key)
        if value:
            return value
        raise ValueError(f"No such env: {key}")
