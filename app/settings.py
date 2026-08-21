"""Typed view over the app's env config, built from ``iduconfig.Config``.

Exists to give the admin config API (``app.system.admin_config_router``) something to
validate a candidate override against before persisting it -- ``iduconfig.Config.get``
itself only ever returns strings, so a bad value (e.g. ``MAX_API_ASYNC_EXTRACTIONS=abc``)
would otherwise only fail deep inside ``int(...)`` at first use.
"""

from __future__ import annotations

import os

from iduconfig import Config
from pydantic import BaseModel, ValidationError

from app.common.config_utils import get_optional_config


class Settings(BaseModel):
    """Resolved application config, typed and validated."""

    log_file: str
    log_level: str
    urban_api: str
    test_urban_api: str
    ecodonut_api: str
    max_api_async_extractions: int
    max_timeout: int = 60
    genplanner_api_base_url: str = "http://localhost:80"
    mcp_server_port: int = 8766
    mcp_upstream_timeout_seconds: float = 300.0
    ollama_base_url: str = ""
    chat_storage_base_url: str = ""
    chat_storage_timeout_seconds: float = 10.0
    keycloak_url: str = ""
    keycloak_realm: str = ""
    keycloak_client_id: str = ""
    keycloak_client_secret: str = ""
    keycloak_scope: str = ""
    llm_provider: str = "vllm"
    vllm_base_url: str = ""
    chat_model: str = ""
    generate_model: str = ""
    app_env: str = "development"
    admin_api_token: str = ""


def build_settings(config: Config) -> Settings:
    """Build a validated :class:`Settings` snapshot from the current process env."""

    return Settings(
        log_file=config.get("LOG_FILE"),
        log_level=config.get("LOG_LEVEL"),
        urban_api=config.get("URBAN_API"),
        test_urban_api=config.get("TEST_URBAN_API"),
        ecodonut_api=config.get("ECODONUT_API"),
        max_api_async_extractions=int(config.get("MAX_API_ASYNC_EXTRACTIONS")),
        max_timeout=int(get_optional_config(config, "MAX_TIMEOUT", "60")),
        genplanner_api_base_url=get_optional_config(config, "GENPLANNER_API_BASE_URL", "http://localhost:80"),
        mcp_server_port=int(get_optional_config(config, "MCP_SERVER_PORT", "8766")),
        mcp_upstream_timeout_seconds=float(get_optional_config(config, "MCP_UPSTREAM_TIMEOUT_SECONDS", "300")),
        ollama_base_url=get_optional_config(config, "OLLAMA_BASE_URL", ""),
        chat_storage_base_url=get_optional_config(config, "CHAT_STORAGE_BASE_URL", ""),
        chat_storage_timeout_seconds=float(get_optional_config(config, "CHAT_STORAGE_TIMEOUT_SECONDS", "10")),
        keycloak_url=get_optional_config(config, "KEYCLOAK_URL", ""),
        keycloak_realm=get_optional_config(config, "KEYCLOAK_REALM", ""),
        keycloak_client_id=get_optional_config(config, "KEYCLOAK_CLIENT_ID", ""),
        keycloak_client_secret=get_optional_config(config, "KEYCLOAK_CLIENT_SECRET", ""),
        keycloak_scope=get_optional_config(config, "KEYCLOAK_SCOPE", ""),
        llm_provider=get_optional_config(config, "LLM_PROVIDER", "vllm"),
        vllm_base_url=get_optional_config(config, "VLLM_BASE_URL", ""),
        chat_model=get_optional_config(config, "CHAT_MODEL", ""),
        generate_model=get_optional_config(config, "GENERATE_MODEL", ""),
        app_env=get_optional_config(config, "APP_ENV", "development"),
        admin_api_token=get_optional_config(config, "ADMIN_API_TOKEN", ""),
    )


def validate_candidate(config: Config, key: str, value: str) -> str | None:
    """Try building Settings with ``key=value`` without persisting it.

    Applies the candidate to this process's env transiently, then always restores the
    previous value -- so a rejected update never touches ``os.environ`` or the override
    store. Returns an error message, or None if the candidate is valid.
    """

    sentinel = object()
    old = os.environ.get(key, sentinel)
    os.environ[key] = value
    try:
        build_settings(config)
        return None
    except (ValidationError, ValueError, TypeError) as exc:
        return str(exc)
    finally:
        if old is sentinel:
            os.environ.pop(key, None)
        else:
            os.environ[key] = old
