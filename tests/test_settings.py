import os

import pytest

from app.settings import build_settings, validate_candidate

REQUIRED_ENV = {
    "LOG_FILE": "genplanner.log",
    "LOG_LEVEL": "INFO",
    "URBAN_API": "https://urban-api.test",
    "TEST_URBAN_API": "https://urban-api.test",
    "ECODONUT_API": "http://ecodonut.test",
    "MAX_API_ASYNC_EXTRACTIONS": "20",
}


class FakeConfig:
    """Stands in for iduconfig.Config, which raises ValueError for missing/empty keys."""

    def __init__(self, values: dict[str, str]):
        self._values = values

    def get(self, key: str) -> str:
        value = self._values.get(key)
        if value:
            return value
        raise ValueError(f"No such env: {key}")


class EnvConfig:
    """Stands in for the real iduconfig.Config, whose .get() reads os.environ directly.

    validate_candidate() works by writing the candidate into os.environ and then calling
    config.get() -- unlike the dict-backed FakeConfig above, this fake must actually read
    os.environ for that mechanism to be exercised.
    """

    @staticmethod
    def get(key: str) -> str:
        value = os.environ.get(key)
        if value:
            return value
        raise ValueError(f"No such env: {key}")


def test_build_settings_reads_required_and_default_fields():
    settings = build_settings(FakeConfig(REQUIRED_ENV))

    assert settings.urban_api == "https://urban-api.test"
    assert settings.max_api_async_extractions == 20
    assert settings.llm_provider == "vllm"  # default, not present in REQUIRED_ENV
    assert settings.keycloak_client_secret == ""


def test_build_settings_raises_when_a_required_key_is_missing():
    incomplete = {k: v for k, v in REQUIRED_ENV.items() if k != "URBAN_API"}

    with pytest.raises(ValueError, match="URBAN_API"):
        build_settings(FakeConfig(incomplete))


def test_build_settings_type_checks_optional_numeric_fields():
    env = {**REQUIRED_ENV, "MCP_UPSTREAM_TIMEOUT_SECONDS": "not-a-number"}

    with pytest.raises(ValueError, match="not-a-number"):
        build_settings(FakeConfig(env))


def test_validate_candidate_accepts_a_valid_value(monkeypatch):
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)

    error = validate_candidate(EnvConfig(), "MAX_API_ASYNC_EXTRACTIONS", "5")

    assert error is None


def test_validate_candidate_rejects_an_invalid_value(monkeypatch):
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)

    error = validate_candidate(EnvConfig(), "MAX_API_ASYNC_EXTRACTIONS", "not-a-number")

    assert error is not None


def test_validate_candidate_never_leaves_the_candidate_in_os_environ(monkeypatch):
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("MAX_API_ASYNC_EXTRACTIONS", raising=False)

    validate_candidate(EnvConfig(), "MAX_API_ASYNC_EXTRACTIONS", "5")

    assert "MAX_API_ASYNC_EXTRACTIONS" not in os.environ
