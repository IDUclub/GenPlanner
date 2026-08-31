import json
from functools import lru_cache
from pathlib import Path

from loguru import logger

from app.common.constants.api_constants import territory_zone_names

from .draft import GenerationDraft

_PROMPT_PATH = Path(__file__).parent / "data" / "chat_system_prompt.txt"


@lru_cache(maxsize=1)
def _load_prompt_template() -> str:
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8")
    except OSError:
        logger.warning(f"Chat system prompt not found at {_PROMPT_PATH}, using minimal fallback")
        return "Ты ассистент GenPlanner.\n\nЗоны:\n{zones_table}\n\nЧерновик:\n{draft_json}\n"


def _build_zones_table() -> str:
    """
    List the territorial zone names the chat may use.

    Names, not ids: the user speaks in zone names and so does the agent's patch --
    GenerationDraft translates them to ids on the way into the DTO.
    """

    return "\n".join(f"- {name}" for name in territory_zone_names())


def build_system_prompt(draft: GenerationDraft) -> str:
    """
    Render the chat system prompt with the current zone reference table and the
    in-progress draft, so the model always sees up-to-date state without needing the
    full conversation history re-parsed for it.
    """

    template = _load_prompt_template()
    return template.replace("{zones_table}", _build_zones_table()).replace(
        "{draft_json}", json.dumps(draft.as_named_dict(), ensure_ascii=False)
    )
