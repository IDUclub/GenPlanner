import json
import os

import pytest

from app.common import config_runtime


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    """
    Points the override store at a throwaway file and clears the in-memory baseline,
    so tests never touch the repo's real config_overrides.json or leak into each other
    through the module-level _baseline dict.
    """

    monkeypatch.setattr(config_runtime, "_OVERRIDES_FILE", tmp_path / "config_overrides.json")
    config_runtime._baseline.clear()
    yield
    config_runtime._baseline.clear()


def test_is_overridable_requires_a_known_env_key(monkeypatch):
    monkeypatch.setenv("SOME_KNOWN_KEY", "1")
    monkeypatch.delenv("SOME_UNKNOWN_KEY", raising=False)

    assert config_runtime.is_overridable("SOME_KNOWN_KEY") is True
    assert config_runtime.is_overridable("SOME_UNKNOWN_KEY") is False


@pytest.mark.parametrize("key", ["ADMIN_API_TOKEN", "KEYCLOAK_CLIENT_SECRET"])
def test_is_overridable_denies_credentials(monkeypatch, key):
    monkeypatch.setenv(key, "secret")

    assert config_runtime.is_overridable(key) is False


def test_set_override_writes_env_and_is_listed(monkeypatch):
    monkeypatch.setenv("MAX_API_ASYNC_EXTRACTIONS", "20")

    config_runtime.set_override("MAX_API_ASYNC_EXTRACTIONS", "5", updated_by="tester")

    assert os.environ["MAX_API_ASYNC_EXTRACTIONS"] == "5"
    overrides = config_runtime.list_overrides()
    assert len(overrides) == 1
    assert overrides[0]["key"] == "MAX_API_ASYNC_EXTRACTIONS"
    assert overrides[0]["value"] == "5"
    assert overrides[0]["updated_by"] == "tester"
    assert overrides[0]["updated_at"]


def test_set_override_persists_to_disk(monkeypatch):
    monkeypatch.setenv("MAX_API_ASYNC_EXTRACTIONS", "20")

    config_runtime.set_override("MAX_API_ASYNC_EXTRACTIONS", "5")

    with config_runtime._OVERRIDES_FILE.open("r", encoding="utf-8") as f:
        stored = json.load(f)
    assert stored["MAX_API_ASYNC_EXTRACTIONS"]["value"] == "5"


def test_delete_override_restores_the_deployed_value(monkeypatch):
    monkeypatch.setenv("MAX_API_ASYNC_EXTRACTIONS", "20")
    config_runtime.set_override("MAX_API_ASYNC_EXTRACTIONS", "5")

    existed = config_runtime.delete_override("MAX_API_ASYNC_EXTRACTIONS")

    assert existed is True
    assert os.environ["MAX_API_ASYNC_EXTRACTIONS"] == "20"
    assert config_runtime.list_overrides() == []


def test_delete_override_missing_key_returns_false():
    assert config_runtime.delete_override("NOT_OVERRIDDEN") is False


def test_apply_overrides_on_startup_reapplies_stored_overrides(monkeypatch):
    monkeypatch.setenv("MAX_API_ASYNC_EXTRACTIONS", "20")
    config_runtime.set_override("MAX_API_ASYNC_EXTRACTIONS", "5")

    # Simulate a fresh process boot: env back to the deployed value, baseline forgotten.
    monkeypatch.setenv("MAX_API_ASYNC_EXTRACTIONS", "20")
    config_runtime._baseline.clear()

    config_runtime.apply_overrides_on_startup()

    assert os.environ["MAX_API_ASYNC_EXTRACTIONS"] == "5"


def test_apply_overrides_on_startup_skips_denied_and_unknown_keys(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "deployed-secret")
    with config_runtime._OVERRIDES_FILE.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "ADMIN_API_TOKEN": {"value": "hijacked", "updated_at": "x", "updated_by": None},
                "STALE_REMOVED_KEY": {"value": "injected", "updated_at": "x", "updated_by": None},
            },
            f,
        )

    config_runtime.apply_overrides_on_startup()

    assert os.environ["ADMIN_API_TOKEN"] == "deployed-secret"
    assert "STALE_REMOVED_KEY" not in os.environ
