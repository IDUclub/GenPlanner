import json

from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator

from app.common.geometries import Geometry
from app.common.exceptions.http_exception import http_exception

with open("app/common/example_geometry.json") as et:
    example_territory =json.load(et)


class GenPlannerDTO(BaseModel):

    territory: Optional[Geometry] = Field(default=None, examples=[example_territory], description="The territory polygon")


class GenPlannerFuncZonesDTO(GenPlannerDTO):

    project_id: int = Field(...,examples=[72], description="The project ID")
    scenario: Literal[
        8, 1, 4, 7, 2, 6, 5, 3
    ] | int = Field(..., examples=[8], description="Scenario func zone type")

    @classmethod
    @field_validator("scenario", mode="before")
    def validate_project_id(cls, v):
        if v.isnumeric():
            return int(v)
        raise http_exception(
            400,
            "Project ID is invalid",
            _input=v,
            _detail="Input should be numeric"
        )

class GenPlannerTerZonesDTO(GenPlannerDTO):
    project_id: int = Field(..., examples=[72], description="Project ID")
    scenario: Literal[
        1, 4, 7, 2, 6, 5, 3
    ] | int = Field(..., examples=[1], description="Scenario ter zone type")

    @classmethod
    @field_validator("scenario", mode="before")
    def validate_project_id(cls, v):
        if v.isnumeric():
            return int(v)
        raise http_exception(
            400,
            "Project ID is invalid",
            _input=v,
            _detail="Input should be numeric"
        )
