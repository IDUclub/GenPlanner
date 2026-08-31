from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.common.constants.api_constants import scenario_func_zones_map


class CustomGenerationDraft(BaseModel):
    """
    In-progress GenPlannerCustomDTO field being assembled across chat turns for the
    custom-territory (no scenario_id) chat.

    Unlike GenerationDraft, custom generation runs a single ready-made zoning profile
    over the whole uploaded territory (GenPlannerCustomDTO.profile_id) rather than an
    arbitrary territory_balance/relation matrix -- run_custom_func_generation doesn't
    support those.

    Persisted as JSON in the latest assistant message's ChatStorage `metadata`, same as
    GenerationDraft.
    """

    profile_id: int | None = Field(default=None)

    @field_validator("profile_id")
    @classmethod
    def validate_profile_id(cls, value: int | None) -> int | None:
        """
        Accept only ids that actually exist in scenario_func_zones_map -- the range
        1..13 is not contiguous (there is no profile 9), so a range check alone lets an
        id through that later blows up with a KeyError inside GenPlannerCustomDTO.
        """

        if value is not None and value not in scenario_func_zones_map:
            raise ValueError(f"Unknown profile_id {value}, available: {sorted(scenario_func_zones_map)}")
        return value

    def merge_patch(self, patch: dict[str, Any]) -> "CustomGenerationDraft":
        """
        Merge a partial update (as decided by the chat agent) into a new draft. A patch
        value of None leaves the existing draft value untouched.
        """

        data = self.model_dump()
        for key in data:
            value = patch.get(key)
            if value is not None:
                data[key] = value
        return CustomGenerationDraft.model_validate(data)

    def is_ready_for_generation(self) -> bool:
        return self.profile_id is not None
