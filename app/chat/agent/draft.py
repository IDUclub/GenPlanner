from typing import Any, Self

from pydantic import BaseModel, Field, model_validator


class GenerationDraft(BaseModel):
    """
    In-progress GenPlannerFuncZonesDTO fields being assembled across chat turns.

    Only covers the parameters a chat can actually set (see the chat-parameter-tiers
    diagram from this feature's design): territory_balance/neighbour_pairs/forbidden_pairs
    directly, min_block_area/elevation_angle/roads_extend_distance via clarifying
    questions. project_id/scenario_id/test/fix_zones/functional_zones are deliberately
    absent -- the first two come from the session (URL + frontend selection), the last
    two are out of MVP scope (need a map / imply "generate from scratch").

    Persisted as JSON in the latest assistant message's ChatStorage `metadata`, so no
    separate database is needed for chat state.
    """

    territory_balance: dict[int, float] | None = None
    neighbour_pairs: list[tuple[int, int]] | None = None
    forbidden_pairs: list[tuple[int, int]] | None = None
    min_block_area: dict[int, float] | None = None
    elevation_angle: int | None = Field(default=None, ge=0, le=90)
    roads_extend_distance: float | None = None

    @model_validator(mode="after")
    def _validate_angle(self) -> Self:
        if self.elevation_angle is not None and not 0 <= self.elevation_angle <= 90:
            self.elevation_angle = None
        return self

    def merge_patch(self, patch: dict[str, Any]) -> "GenerationDraft":
        """
        Merge a partial update (as decided by the chat agent) into a new draft. Only
        known fields are applied; a patch value of None leaves the existing draft value
        untouched (the agent omits fields it isn't changing rather than clearing them).
        """

        data = self.model_dump()
        for key in data:
            value = patch.get(key)
            if value is not None:
                data[key] = value
        return GenerationDraft.model_validate(data)

    def is_ready_for_generation(self) -> bool:
        """territory_balance is the only field GenPlannerFuncZonesDTO requires."""

        return bool(self.territory_balance)
