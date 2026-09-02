import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.common import config_runtime
from app.dependencies import get_config
from app.system.admin_config_router import router as admin_config_router

ADMIN_TOKEN = "local-admin-secret"
ADMIN_HEADERS = {"X-Admin-Token": ADMIN_TOKEN}

REQUIRED_ENV = {
    "LOG_FILE": "genplanner.log",
    "LOG_LEVEL": "INFO",
    "URBAN_API": "https://urban-api.test",
    "TEST_URBAN_API": "https://urban-api.test",
    "ECODONUT_API": "http://ecodonut.test",
    "MAX_API_ASYNC_EXTRACTIONS": "20",
}


class _EnvConfig:
    """Stands in for iduconfig.Config, whose .get() is itself a thin os.environ wrapper."""

    @staticmethod
    def get(key: str) -> str:
        value = os.environ.get(key)
        if value:
            return value
        raise ValueError(f"No such env: {key}")


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    """Points the override store at a throwaway file and clears the in-memory baseline."""

    monkeypatch.setattr(config_runtime, "_OVERRIDES_FILE", tmp_path / "config_overrides.json")
    config_runtime._baseline.clear()
    yield
    config_runtime._baseline.clear()


@pytest.fixture
def client(monkeypatch):
    async def _fake_rebuild(app):
        return None

    # The router rebuilds live app state (urban/LLM/Keycloak clients) after every
    # change; that rebuild needs a fully wired FastAPI app, which this router-only
    # test app doesn't have, so it's replaced with a no-op here.
    monkeypatch.setattr("app.system.admin_config_router.rebuild_runtime_state", _fake_rebuild)

    app = FastAPI()
    app.include_router(admin_config_router)
    app.dependency_overrides[get_config] = lambda: _EnvConfig()

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def admin_env(monkeypatch):
    """Baseline env the admin API needs to be enabled and Settings to build cleanly."""

    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("ADMIN_API_TOKEN", ADMIN_TOKEN)


def test_returns_503_when_admin_token_not_configured(client, monkeypatch):
    monkeypatch.delenv("ADMIN_API_TOKEN", raising=False)

    response = client.get("/admin/config/settings", headers=ADMIN_HEADERS)

    assert response.status_code == 503


def test_returns_401_for_wrong_token(client, admin_env):
    response = client.get("/admin/config/settings", headers={"X-Admin-Token": "wrong"})

    assert response.status_code == 401


def test_returns_401_when_token_header_missing(client, admin_env):
    response = client.get("/admin/config/settings")

    assert response.status_code == 401


def test_resolved_settings_masks_secrets(client, admin_env, monkeypatch):
    monkeypatch.setenv("KEYCLOAK_CLIENT_SECRET", "super-secret")

    response = client.get("/admin/config/settings", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["admin_api_token"] == "***"
    assert body["keycloak_client_secret"] == "***"


def test_put_rejects_a_credential_key(client, admin_env, monkeypatch):
    monkeypatch.setenv("KEYCLOAK_CLIENT_SECRET", "super-secret")

    response = client.put("/admin/config/KEYCLOAK_CLIENT_SECRET", json={"value": "hijacked"}, headers=ADMIN_HEADERS)

    assert response.status_code == 400
    assert os.environ["KEYCLOAK_CLIENT_SECRET"] == "super-secret"


def test_put_rejects_an_unknown_key(client, admin_env):
    response = client.put("/admin/config/SOME_NEW_KEY", json={"value": "x"}, headers=ADMIN_HEADERS)

    assert response.status_code == 400


def test_put_rejects_a_value_that_fails_typed_validation(client, admin_env):
    response = client.put(
        "/admin/config/MAX_API_ASYNC_EXTRACTIONS", json={"value": "not-a-number"}, headers=ADMIN_HEADERS
    )

    assert response.status_code == 400
    assert os.environ["MAX_API_ASYNC_EXTRACTIONS"] == "20"
    assert config_runtime.list_overrides() == []


def test_put_then_get_then_delete_roundtrip(client, admin_env):
    put_response = client.put(
        "/admin/config/MAX_API_ASYNC_EXTRACTIONS",
        json={"value": "5", "updated_by": "tester"},
        headers=ADMIN_HEADERS,
    )
    assert put_response.status_code == 200
    put_body = put_response.json()
    assert put_body["overridden"] is True
    assert put_body["override_value"] == "5"
    assert put_body["updated_by"] == "tester"
    assert os.environ["MAX_API_ASYNC_EXTRACTIONS"] == "5"

    get_response = client.get("/admin/config/MAX_API_ASYNC_EXTRACTIONS", headers=ADMIN_HEADERS)
    assert get_response.status_code == 200
    assert get_response.json()["effective"] == "5"

    delete_response = client.delete("/admin/config/MAX_API_ASYNC_EXTRACTIONS", headers=ADMIN_HEADERS)
    assert delete_response.status_code == 200
    assert delete_response.json()["overridden"] is False
    assert os.environ["MAX_API_ASYNC_EXTRACTIONS"] == "20"


def test_delete_of_a_missing_override_returns_404(client, admin_env):
    response = client.delete("/admin/config/MAX_API_ASYNC_EXTRACTIONS", headers=ADMIN_HEADERS)

    assert response.status_code == 404


def test_overrides_listing_reflects_active_overrides(client, admin_env):
    client.put("/admin/config/MAX_API_ASYNC_EXTRACTIONS", json={"value": "5"}, headers=ADMIN_HEADERS)

    response = client.get("/admin/config/overrides", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["overrides"][0]["key"] == "MAX_API_ASYNC_EXTRACTIONS"
