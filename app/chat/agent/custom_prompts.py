import json
from functools import lru_cache
from pathlib import Path

from loguru import logger

from app.common.constants.api_constants import profile_names

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
    """
    List the zoning profile names the chat may use.

    Names, not ids: CustomGenerationDraft resolves the chosen name back to the profile id
    GenPlannerCustomDTO needs.
    """

    return "\n".join(f"- {name}" for name in profile_names())


def build_custom_system_prompt(draft: CustomGenerationDraft) -> str:
    """
    Render the custom-territory chat system prompt with the current profile reference
    table and the in-progress draft.
    """

    template = _load_prompt_template()
    return template.replace("{zones_table}", _build_zones_table()).replace(
        "{draft_json}", json.dumps(draft.as_named_dict(), ensure_ascii=False)
    )
