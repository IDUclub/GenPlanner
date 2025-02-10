import json

from typing import Literal, Optional, Self
from pydantic import BaseModel, Field, field_validator, model_validator

from app.common.geometries import Geometry
from app.common.exceptions.http_exception import http_exception

with open("app/common/example_geometry.json") as et:
    example_territory =json.load(et)


class GenPlannerDTO(BaseModel):

    project_id: Optional[int] = Field(default=None, examples=[72], description="The project ID")
    territory: Optional[Geometry] = Field(default=None, examples=[example_territory], description="The territory polygon")

    @model_validator(mode="after")
    def validate_territory(self) -> Self:

        if self.territory and self.project_id:
            raise http_exception(
                status_code=400,
                msg="Can pass either geojson territory or project ID (strict or)",
                _input={
                    "territory": self.territory.__dict__,
                    "project_id": self.project_id,
                },
                _detail=None
            )
        elif not self.territory and not self.project_id:
            raise http_exception(
                status_code=400,
                msg="Have to pass either geojson territory or project ID (strict or)",
                _input={
                    "territory": self.territory,
                    "project_id": self.project_id,
                },
                _detail=None
            )
        else:
            return self


class GenPlannerFuncZonesDTO(GenPlannerDTO):

    scenario: Literal[
        8, 1, 4, 7, 2, 6, 5, 3
    ] | int = Field(..., description="Scenario func zone type")


class GenPlannerTerZonesDTO(GenPlannerDTO):

    scenario: Literal[
        1, 4, 7, 2, 6, 5, 3
    ] | int = Field(..., description="Scenario ter zone type")
