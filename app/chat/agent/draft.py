from typing import Any, Self

from pydantic import BaseModel, Field, model_validator

from app.common.constants.api_constants import territory_zone_name_by_id

from .zone_refs import resolve_zone_pairs, resolve_zone_ratio_map


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

        Zone references arrive as names («жилая»), which is what the agent and the user
        talk in, and are resolved to ids here -- the draft itself stays id-keyed so the
        DTO it feeds and drafts already stored in chat history keep the same shape.
        """

        normalized = _resolve_zone_references(patch)

        data = self.model_dump()
        for key in data:
            value = normalized.get(key)
            if value is not None:
                data[key] = value
        return GenerationDraft.model_validate(data)

    def as_named_dict(self) -> dict[str, Any]:
        """
        The draft with zone ids rendered back as names, for showing it in the system
        prompt. The prompt tells the model to speak names only -- handing it a draft full
        of ids would contradict that and invite it to echo ids back at the user.
        """

        def name(zone_id: int) -> str:
            return territory_zone_name_by_id(zone_id) or str(zone_id)

        data: dict[str, Any] = {}
        if self.territory_balance:
            data["territory_balance"] = {name(zone_id): ratio for zone_id, ratio in self.territory_balance.items()}
        if self.min_block_area:
            data["min_block_area"] = {name(zone_id): area for zone_id, area in self.min_block_area.items()}
        for field, pairs in (
            ("neighbour_pairs", self.neighbour_pairs or []),
            ("forbidden_pairs", self.forbidden_pairs or []),
        ):
            if pairs:
                data[field] = [[name(left), name(right)] for left, right in pairs]
        if self.elevation_angle is not None:
            data["elevation_angle"] = self.elevation_angle
        if self.roads_extend_distance is not None:
            data["roads_extend_distance"] = self.roads_extend_distance
        return data

    def is_ready_for_generation(self) -> bool:
        """territory_balance is the only field GenPlannerFuncZonesDTO requires."""

        return bool(self.territory_balance)


def _resolve_zone_references(patch: dict[str, Any]) -> dict[str, Any]:
    """
    Return a copy of the agent's patch with every zone-keyed field turned into zone ids.

    Fields that resolve to nothing are left out entirely (not set to an empty value), so
    a hallucinated zone name never wipes a balance the user already agreed on.
    """

    normalized = dict(patch)
    for field in ("territory_balance", "min_block_area"):
        if field in normalized:
            normalized[field] = resolve_zone_ratio_map(normalized[field])
    for field in ("neighbour_pairs", "forbidden_pairs"):
        if field in normalized:
            normalized[field] = resolve_zone_pairs(normalized[field])
    return normalized
