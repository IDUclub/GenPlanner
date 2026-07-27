import pytest
from fastmcp.exceptions import AuthorizationError

from app.mcp_server.auth import AnyTokenVerifier, extract_token


def test_extract_token_strips_bearer_prefix(monkeypatch):
    monkeypatch.setattr(
        "app.mcp_server.auth.get_http_headers",
        lambda **kwargs: {"authorization": "Bearer abc123"},
    )

    assert extract_token() == "abc123"


def test_extract_token_raises_when_header_missing(monkeypatch):
    monkeypatch.setattr("app.mcp_server.auth.get_http_headers", lambda **kwargs: {})

    with pytest.raises(ValueError, match="Bearer token is missing"):
        extract_token()


def test_extract_token_raises_when_header_not_bearer_scheme(monkeypatch):
    monkeypatch.setattr(
        "app.mcp_server.auth.get_http_headers",
        lambda **kwargs: {"authorization": "Basic abc123"},
    )

    with pytest.raises(ValueError, match="Bearer token is missing"):
        extract_token()


async def test_any_token_verifier_accepts_non_empty_token():
    verifier = AnyTokenVerifier()

    access_token = await verifier.verify_token("some-token")

    assert access_token.token == "some-token"


async def test_any_token_verifier_rejects_empty_token():
    verifier = AnyTokenVerifier()

    with pytest.raises(AuthorizationError):
        await verifier.verify_token("")
