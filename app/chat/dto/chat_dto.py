from pydantic import BaseModel, Field, field_validator

from app.common.constants.api_constants import default_terr_zones_map

_PAIRS_DESCRIPTION = (
    "Territorial zone id pairs set from the frontend matrix, same format as on GenPlannerFuncZonesDTO. "
    "Omit or null to keep the chat's current pairs, [] to reset them to the default matrix. "
    "Overrides pairs the agent parsed from this turn's text and is kept in the chat draft for later turns."
)


class ChatTurnDTO(BaseModel):
    """
    DTO for a single chat turn.
    Attributes:
        user_query (str): The user's message for this turn.
        chat_id (str | None): Existing ChatStorage chat id; omit to start a new chat.
        test (bool): Route generation through the test Urban API, same as the DTO field on
            GenPlannerFuncZonesDTO -- project_id/scenario_id still come from the URL/session,
            never from chat text.
        neighbour_pairs (list[tuple[int, int]] | None): Zone id pairs to encourage as neighbours.
        forbidden_pairs (list[tuple[int, int]] | None): Zone id pairs to discourage as neighbours.
    """

    user_query: str = Field(min_length=1, examples=["Хочу 50% жильё, 30% бизнес и 20% рекреации"])
    chat_id: str | None = Field(default=None, description="Existing chat id; omit to start a new chat")
    test: bool = Field(default=False, description="Route generation through the test Urban API")
    neighbour_pairs: list[tuple[int, int]] | None = Field(
        default=None, description=_PAIRS_DESCRIPTION, examples=[[(1, 2)]]
    )
    forbidden_pairs: list[tuple[int, int]] | None = Field(
        default=None, description=_PAIRS_DESCRIPTION, examples=[[(1, 6)]]
    )

    @field_validator("neighbour_pairs", "forbidden_pairs")
    @classmethod
    def _check_zone_ids(cls, pairs: list[tuple[int, int]] | None) -> list[tuple[int, int]] | None:
        if pairs is None:
            return None
        unknown = sorted({zone_id for pair in pairs for zone_id in pair if str(zone_id) not in default_terr_zones_map})
        if unknown:
            raise ValueError(f"Unknown territorial zone ids: {unknown}")
        return pairs
