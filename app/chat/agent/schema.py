"""
JSON Schema constraining the chat agent's one-call-per-turn decision step
(ChatClient.complete_json -- vLLM's `response_format.json_schema`, Ollama's `format`).
A single call returns both the action to execute and the ready-to-stream reply text --
no second "reply" call.

Zones are referred to by name, not by id: the enums below are the exact vocabulary the
model may answer with, so constrained decoding cannot invent a zone that does not exist.
GenerationDraft maps the names back to ids on merge.
"""

from app.common.constants.api_constants import territory_zone_names

_ZONE_NAME_SCHEMA: dict = {
    "type": "string",
    "enum": territory_zone_names(),
    "description": "Territorial zone name, spelled exactly as in the enum -- never an id.",
}

AGENT_ACTION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["update_draft", "ask_clarifying_question", "run_generation", "list_zones", "chat"],
            "description": (
                "update_draft: user gave new/changed generation parameters, nothing else to do yet. "
                "ask_clarifying_question: need more info before updating or running. "
                "run_generation: user confirmed (or gave a complete balance and asked to run immediately) "
                "and territory_balance will be set (from patch this turn and/or an earlier turn) -- start "
                "generation now. "
                "list_zones: user asked what zones are available. "
                "chat: anything else (greeting, off-topic, explanation)."
            ),
        },
        "patch": {
            "type": "object",
            "description": (
                "Partial GenerationDraft update. Always include any new/changed fields the user just gave, "
                "even when action=run_generation in the same turn (e.g. user provides territory_balance and "
                "asks to run right away) -- it is merged before generation is attempted."
            ),
            "properties": {
                "territory_balance": {
                    "type": "object",
                    "additionalProperties": {"type": "number", "exclusiveMinimum": 0},
                    "description": (
                        'Territorial zone name (as key, e.g. "жилая") -> target ratio. Use only the names listed '
                        "in the system prompt."
                    ),
                },
                "neighbour_pairs": {
                    "type": "array",
                    "items": {"type": "array", "items": _ZONE_NAME_SCHEMA, "minItems": 2, "maxItems": 2},
                    "description": "Pairs of zone names that should be neighbours.",
                },
                "forbidden_pairs": {
                    "type": "array",
                    "items": {"type": "array", "items": _ZONE_NAME_SCHEMA, "minItems": 2, "maxItems": 2},
                    "description": "Pairs of zone names that must not be neighbours.",
                },
                "min_block_area": {
                    "type": "object",
                    "additionalProperties": {"type": "number", "exclusiveMinimum": 0},
                    "description": (
                        "Territorial zone name (as key) -> minimum block area in m^2. Use only the names "
                        "listed in the system prompt."
                    ),
                },
                "elevation_angle": {"type": "integer", "minimum": 0, "maximum": 90},
                "roads_extend_distance": {"type": "number", "exclusiveMinimum": 0},
            },
        },
        "reply": {
            "type": "string",
            "description": "Ready-to-show response to the user, in Russian.",
        },
    },
    "required": ["action", "reply"],
}


CHAT_TITLE_SCHEMA: dict = {
    "type": "string",
    "description": (
        "Short Russian title for this new chat: a 2-5 word noun phrase naming what the user wants "
        "(e.g. «Зонирование с упором на жильё»), never a greeting, a whole sentence, a question, "
        "quotes or a trailing period. Asked for only on the first turn of a chat."
    ),
}


def with_chat_title(schema: dict) -> dict:
    """
    Same schema plus a required `chat_title`, for the first turn of a new chat.

    Length is not constrained here on purpose: not every constrained-decoding backend
    honours minLength/maxLength, and the caller shortens the title anyway.
    """

    return {
        **schema,
        "properties": {**schema["properties"], "chat_title": CHAT_TITLE_SCHEMA},
        "required": [*schema["required"], "chat_title"],
    }


def build_agent_action_schema(include_chat_title: bool = False) -> dict:
    """Per-turn schema: the base decision schema, plus `chat_title` when the chat is new."""

    return with_chat_title(AGENT_ACTION_SCHEMA) if include_chat_title else AGENT_ACTION_SCHEMA
