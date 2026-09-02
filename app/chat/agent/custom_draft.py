from typing import Any

from loguru import logger
from pydantic import BaseModel, Field, field_validator

from app.common.constants.api_constants import profile_name_by_id, resolve_profile_id, scenario_func_zones_map


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

        The agent names the profile («жилая») rather than numbering it, so `profile` is
        the field it fills; `profile_id` is still accepted for drafts restored from chat
        history and for models that fall back to an id. An unknown profile is dropped,
        leaving the previous choice intact instead of storing an id generation would
        reject.
        """

        requested = patch.get("profile")
        if requested is None:
            requested = patch.get("profile_id")

        data = self.model_dump()
        if requested is not None:
            profile_id = resolve_profile_id(requested)
            if profile_id is None:
                logger.warning(f"custom chat agent picked an unknown profile {requested!r}, keeping the previous one")
            else:
                data["profile_id"] = profile_id
        return CustomGenerationDraft.model_validate(data)

    def as_named_dict(self) -> dict[str, Any]:
        """
        The draft with the profile id rendered back as its name, for showing it in the
        system prompt -- which tells the model to speak profile names only.
        """

        if self.profile_id is None:
            return {}
        return {"profile": profile_name_by_id(self.profile_id) or str(self.profile_id)}

    def is_ready_for_generation(self) -> bool:
        return self.profile_id is not None
