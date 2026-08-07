from functools import lru_cache
from pathlib import Path

from loguru import logger

from app.common.constants.api_constants import default_terr_zones_map, territory_zone_kind_names_ru

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
    """List every default territorial zone id with a human-readable (Russian) kind name."""

    lines = []
    for zone_id, zone in sorted(default_terr_zones_map.items(), key=lambda kv: int(kv[0])):
        name = territory_zone_kind_names_ru.get(zone.kind, zone.kind.value)
        lines.append(f"{zone_id} — {name}")
    return "\n".join(lines)


def build_system_prompt(draft: GenerationDraft) -> str:
    """
    Render the chat system prompt with the current zone reference table and the
    in-progress draft, so the model always sees up-to-date state without needing the
    full conversation history re-parsed for it.
    """

    template = _load_prompt_template()
    return template.replace("{zones_table}", _build_zones_table()).replace(
        "{draft_json}", draft.model_dump_json(exclude_none=True)
    )
