"""
JSON Schema constraining the custom-territory chat agent's one-call-per-turn decision
step. Mirrors AGENT_ACTION_SCHEMA, but patch carries a single profile_id instead of a
territory_balance/relation matrix, since run_custom_func_generation only supports one
ready-made zoning profile applied to the whole uploaded territory.
"""

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
                "list_zones: user asked what profiles/ids are available. "
                "chat: anything else (greeting, off-topic, explanation)."
            ),
        },
        "patch": {
            "type": "object",
            "description": (
                "Partial CustomGenerationDraft update. Always include profile_id when the user just picked "
                "or changed it, even when action=run_generation in the same turn -- it is merged before "
                "generation is attempted."
            ),
            "properties": {
                "profile_id": {
                    "type": "integer",
                    "description": "Zoning profile id to apply to the whole uploaded territory.",
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
