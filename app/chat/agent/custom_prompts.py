from functools import lru_cache
from pathlib import Path

from loguru import logger

from app.common.constants.api_constants import build_zones_reference

from .custom_draft import CustomGenerationDraft

_PROMPT_PATH = Path(__file__).parent / "data" / "chat_custom_system_prompt.txt"


@lru_cache(maxsize=1)
def _load_prompt_template() -> str:
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8")
    except OSError:
        logger.warning(f"Custom chat system prompt not found at {_PROMPT_PATH}, using minimal fallback")
        return "Ты ассистент GenPlanner.\n\nПрофили:\n{zones_table}\n\nЧерновик:\n{draft_json}\n"


def _build_zones_table() -> str:
    """List every generatable zoning profile id with a human-readable (Russian) name."""

    lines = [f"{entry['id']} — {entry['name']}" for entry in build_zones_reference()]
    return "\n".join(lines)


def build_custom_system_prompt(draft: CustomGenerationDraft) -> str:
    """
    Render the custom-territory chat system prompt with the current profile reference
    table and the in-progress draft.
    """

    template = _load_prompt_template()
    return template.replace("{zones_table}", _build_zones_table()).replace(
        "{draft_json}", draft.model_dump_json(exclude_none=True)
    )
