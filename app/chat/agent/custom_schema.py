"""
JSON Schema constraining the custom-territory chat agent's one-call-per-turn decision
step. Mirrors AGENT_ACTION_SCHEMA, but patch carries a single zoning profile instead of a
territory_balance/relation matrix, since run_custom_func_generation only supports one
ready-made zoning profile applied to the whole uploaded territory.

The profile is named, not numbered: the enum below is the exact vocabulary the model may
answer with, so constrained decoding cannot invent a profile that does not exist (which
is what free-form ids allowed). CustomGenerationDraft maps the name back to an id.
"""

from app.common.constants.api_constants import profile_names

from .schema import with_chat_title

CUSTOM_AGENT_ACTION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["update_draft", "ask_clarifying_question", "run_generation", "list_zones", "chat"],
            "description": (
                "update_draft: user picked/changed a zoning profile, nothing else to do yet. "
                "ask_clarifying_question: need more info before picking a profile or running. "
                "run_generation: user confirmed a profile (from patch this turn and/or an earlier turn) -- "
                "start generation now. "
                "list_zones: user asked what zoning profiles are available. "
                "chat: anything else (greeting, off-topic, explanation)."
            ),
        },
        "patch": {
            "type": "object",
            "description": (
                "Partial CustomGenerationDraft update. Always include profile when the user just picked "
                "or changed it, even when action=run_generation in the same turn -- it is merged before "
                "generation is attempted."
            ),
            "properties": {
                "profile": {
                    "type": "string",
                    "enum": profile_names(),
                    "description": (
                        "Name of the zoning profile to apply to the whole uploaded territory, exactly as "
                        "spelled in the enum -- never an id."
                    ),
                },
            },
        },
        "reply": {
            "type": "string",
            "description": "Ready-to-show response to the user, in Russian.",
        },
    },
    "required": ["action", "reply"],
}


def build_custom_agent_action_schema(include_chat_title: bool = False) -> dict:
    """Per-turn schema: the base decision schema, plus `chat_title` when the chat is new."""

    return with_chat_title(CUSTOM_AGENT_ACTION_SCHEMA) if include_chat_title else CUSTOM_AGENT_ACTION_SCHEMA
