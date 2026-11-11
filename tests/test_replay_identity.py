"""Replay ownership survives token renewal without trusting unsigned claims."""

import aiohttp
import pytest
from fastapi import HTTPException

from app.resumable_streams import keycloak_owner, token_owner


@pytest.mark.asyncio
async def test_verified_owner_survives_renewal(monkeypatch):
    class Response:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def json(self):
            return {"sub": "same-user"}

    class Session(Response):
        def __init__(self, **kwargs):
            pass

        def get(self, url, *, headers, allow_redirects):
            assert url == "https://issuer/realms/IDU/protocol/openid-connect/userinfo"
            assert headers["Authorization"] in ("Bearer old", "Bearer renewed")
            assert allow_redirects is False
            return Response()

    monkeypatch.setattr(aiohttp, "ClientSession", Session)
    before = await keycloak_owner("old", "https://issuer", "IDU")
    after = await keycloak_owner("renewed", "https://issuer/", "IDU")
    assert before == after


@pytest.mark.asyncio
@pytest.mark.parametrize("status, expected", [(401, 401), (403, 401), (500, 503), (302, 503)])
async def test_bad_token_or_issuer_never_falls_back_to_unverified_identity(monkeypatch, status, expected):
    class Session:
        def __init__(self, **kwargs):
            self.status = status

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def get(self, *args, **kwargs):
            return self

    monkeypatch.setattr(aiohttp, "ClientSession", Session)
    with pytest.raises(HTTPException) as exc:
        await keycloak_owner("forged-or-expired", "https://issuer", "IDU")
    assert exc.value.status_code == expected


@pytest.mark.asyncio
async def test_unconfigured_identity_is_bound_to_exact_token():
    assert await keycloak_owner("opaque", "", "") == token_owner("opaque")
    assert await keycloak_owner("renewed", "", "") != token_owner("opaque")
