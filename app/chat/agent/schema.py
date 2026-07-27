"""
JSON Schema passed as Ollama's `format` field for the chat agent's one-call-per-turn
decision step (OllamaChatClient.complete_json). A single call returns both the action
to execute and the ready-to-stream reply text -- no second "reply" call.
"""

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
                "list_zones: user asked what zones/ids are available. "
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
                    "description": "Territorial zone id (as string key) -> target ratio.",
                },
                "neighbour_pairs": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2},
                },
                "forbidden_pairs": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2},
                },
                "min_block_area": {
                    "type": "object",
                    "additionalProperties": {"type": "number", "exclusiveMinimum": 0},
                    "description": "Territorial zone id (as string key) -> minimum block area in m^2.",
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
