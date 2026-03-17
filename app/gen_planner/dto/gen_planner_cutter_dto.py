from typing import Literal, Optional, Self

from pydantic import BaseModel, Field

class PolygonCutterDTO(BaseModel):
    scenario_id: int = Field(examples=[835], description="The scenario ID")
    project_id: int | None = Field(default=None, exclude=True)
    roads_extend_distance: float | None = Field(
        default=None,
        description="Optional roads extend distance for territory cutting",
        examples=[5.0],
    )
