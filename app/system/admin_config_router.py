"""Admin API for runtime config overrides -- ``/admin/config/*``.

View / set / delete env vars live (no redeploy). Overrides are persisted to
``config_overrides.json`` and applied directly to this process's env; the config-derived
app state (urban/ecodonut/LLM/Keycloak/ChatStorage clients) is rebuilt right after each
change (see ``app.init_dependencies.rebuild_runtime_state``).

Guarded by the ``ADMIN_API_TOKEN`` shared secret, passed as the ``X-Admin-Token``
header. Credentials are never editable or masked -- see ``app.common.config_runtime``.
"""

from __future__ import annotations

import hmac
import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from iduconfig import Config
from loguru import logger
from pydantic import BaseModel, Field

from app.common.config_runtime import delete_override, is_overridable, list_overrides, set_override
from app.common.config_utils import get_optional_config
from app.dependencies import get_config
from app.init_dependencies import rebuild_runtime_state
from app.settings import build_settings, validate_candidate

router = APIRouter(prefix="/admin/config", tags=["admin"])

# Settings fields that hold secrets -- masked in the resolved-settings view.
_SECRET_SETTING_FIELDS = frozenset({"admin_api_token", "keycloak_client_secret"})


def verify_admin(
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
    config: Config = Depends(get_config),
) -> bool:
    """Gate every admin-config route on the shared ADMIN_API_TOKEN secret."""

    expected = get_optional_config(config, "ADMIN_API_TOKEN")
    if not expected:
        raise HTTPException(status_code=503, detail="Admin config API is disabled (ADMIN_API_TOKEN not set)")
    if not x_admin_token or not hmac.compare_digest(x_admin_token, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing X-Admin-Token")
    return True


class ConfigValueIn(BaseModel):
    """Request body for PUT /admin/config/{key}."""

    value: str = Field(..., description="New string value for the env key")
    updated_by: str | None = Field(default=None, description="Optional audit label")


def _key_view(key: str) -> dict[str, Any]:
    overrides = {o["key"]: o for o in list_overrides()}
    ov = overrides.get(key)
    return {
        "key": key,
        "effective": os.environ.get(key),
        "overridden": ov is not None,
        "override_value": ov["value"] if ov else None,
        "overridable": is_overridable(key),
        "updated_at": ov["updated_at"] if ov else None,
        "updated_by": ov["updated_by"] if ov else None,
    }


@router.get("/settings", dependencies=[Depends(verify_admin)])
def get_resolved_settings(config: Config = Depends(get_config)) -> dict[str, Any]:
    """Resolved, typed application settings the app is actually using (secrets masked)."""

    data = build_settings(config).model_dump()
    for field in _SECRET_SETTING_FIELDS:
        if data.get(field):
            data[field] = "***"
    return data


@router.get("/overrides", dependencies=[Depends(verify_admin)])
def get_active_overrides() -> dict[str, Any]:
    """Only the keys currently overridden (with audit metadata)."""

    items = list_overrides()
    return {"count": len(items), "overrides": items}


@router.get("/{key}", dependencies=[Depends(verify_admin)])
def get_config_key(key: str) -> dict[str, Any]:
    """Effective value + override status for a single env key."""

    return _key_view(key)


@router.put("/{key}", dependencies=[Depends(verify_admin)])
async def put_config_key(
    key: str, body: ConfigValueIn, request: Request, config: Config = Depends(get_config)
) -> dict[str, Any]:
    """Set (or replace) a runtime override for one key.

    Rejects credentials and unknown keys. The new value is validated by rebuilding
    Settings; on a parse error the override is rejected before it's ever persisted.
    """

    if not is_overridable(key):
        raise HTTPException(
            status_code=400,
            detail=f"Key '{key}' is not overridable (unknown env key or a credential).",
        )
    error = validate_candidate(config, key, body.value)  # pre-check, never persists a bad value
    if error is not None:
        raise HTTPException(status_code=400, detail=f"Value rejected for '{key}': {error}")

    set_override(key, body.value, updated_by=body.updated_by)
    await rebuild_runtime_state(request.app)
    logger.info(f"admin_config set key={key} updated_by={body.updated_by or ''}")
    return _key_view(key)


@router.delete("/{key}", dependencies=[Depends(verify_admin)])
async def delete_config_key(key: str, request: Request) -> dict[str, Any]:
    """Remove a runtime override, reverting the key to its deployed value."""

    existed = delete_override(key)
    if not existed:
        raise HTTPException(status_code=404, detail=f"No override set for '{key}'")

    await rebuild_runtime_state(request.app)
    logger.info(f"admin_config delete key={key}")
    return _key_view(key)
