"""Runtime config overrides, persisted to a local JSON file.

``iduconfig.Config.get``/``Config.set`` are thin ``os.environ`` wrappers, so applying
an override only means writing into ``os.environ`` -- every ``config.get(key)`` call
anywhere in the app sees it immediately. Overrides are additionally persisted to
``runtime_data/config_overrides.json`` so they survive a container restart. The file
lives inside a directory bind mount rather than being mounted directly, because the
atomic tmp-file-then-rename write pattern below fails with ``EBUSY`` when the target
path is itself a Docker file bind-mount point.

Safety:
- credentials are never overridable (``_DENY``);
- only keys that already exist in the process env can be overridden (you tune known
  config, you don't inject arbitrary variables).

Single-process scope: GenPlanner runs one gunicorn worker per container and the admin
API only targets the main API process (not the separate ``mcp`` container), so there is
no cross-process sync to do -- an override is applied to ``os.environ`` the moment it's
written, no polling loop needed.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_OVERRIDES_FILE = Path("runtime_data/config_overrides.json")

_DENY: frozenset[str] = frozenset({"ADMIN_API_TOKEN", "KEYCLOAK_CLIENT_SECRET"})

_lock = threading.RLock()
# key -> the env value before it was first overridden (None == key was absent)
_baseline: dict[str, str | None] = {}


def is_overridable(key: str) -> bool:
    """A key is tunable at runtime only if it's known config and not a credential."""

    return key not in _DENY and key in os.environ


def _read_store() -> dict[str, dict[str, Any]]:
    if not _OVERRIDES_FILE.exists():
        return {}
    with _OVERRIDES_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_store(data: dict[str, dict[str, Any]]) -> None:
    _OVERRIDES_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = _OVERRIDES_FILE.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)
    tmp_path.replace(_OVERRIDES_FILE)


def apply_overrides_on_startup() -> None:
    """Capture the deployed baseline and apply any stored overrides.

    Called once at process startup, before the admin API can receive a request, so
    ``_baseline`` reflects the actual deployed value for this boot.
    """

    with _lock:
        store = _read_store()
        for key, entry in store.items():
            if key in _DENY or key not in os.environ:
                continue
            if key not in _baseline:
                _baseline[key] = os.environ.get(key)
            os.environ[key] = entry["value"]


def list_overrides() -> list[dict[str, Any]]:
    """All active overrides as plain dicts (for the admin view)."""

    with _lock:
        store = _read_store()
    return [{"key": key, **entry} for key, entry in sorted(store.items())]


def set_override(key: str, value: str, updated_by: str | None = None) -> None:
    """Persist and immediately apply a runtime override for ``key``."""

    with _lock:
        store = _read_store()
        if key not in _baseline:
            _baseline[key] = os.environ.get(key)
        store[key] = {
            "value": value,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": updated_by,
        }
        _write_store(store)
        os.environ[key] = value


def delete_override(key: str) -> bool:
    """Remove a runtime override, reverting ``key`` to its deployed value.

    Returns:
        bool: True if an override existed for ``key``.
    """

    with _lock:
        store = _read_store()
        if key not in store:
            return False
        del store[key]
        _write_store(store)
        base = _baseline.pop(key, None)
        if base is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = base
    return True
