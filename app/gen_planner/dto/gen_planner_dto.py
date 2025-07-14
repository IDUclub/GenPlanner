import json
from pathlib import Path
from typing import Optional, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from app.common.exceptions.http_exception import http_exception
from app.common.geometries_dto.geometries import FixZoneFeatureCollection, PolygonalFeatureCollection

folder_path = Path(__file__).parent.absolute()

with open(folder_path / "examples/territory_balance_example.json") as tbe:
    territory_balance_example = json.load(tbe)


class GenPlannerDTO(BaseModel):

    project_id: Optional[int] = Field(default=None, examples=[72], description="The project ID")
    scenario_id: Optional[int] = Field(default=None, examples=[72], description="The scenario ID")
    territory_balance: Optional[dict[str | int, float]] = Field(default=None, examples=[territory_balance_example])
    territory: Optional[PolygonalFeatureCollection] = Field(default=None, description="The territory geometry")
    fix_zones: Optional[FixZoneFeatureCollection] = Field(default=None, description="The fix zone geometry")

    @model_validator(mode="after")
    def validate_territory(self) -> Self:

        if self.territory and self.project_id:
            raise http_exception(
                status_code=400,
                msg="Can pass either geojson territory or project ID (strict or)",
                _input={
                    "territory": self.territory.as_geo_dict(),
                    "project_id": self.project_id,
                },
                _detail=None,
            )
        elif not self.territory and not self.project_id:
            raise http_exception(
                status_code=400,
                msg="Have to pass either geojson territory or project ID (strict or)",
                _input={
                    "territory": self.territory,
                    "project_id": self.project_id,
                },
                _detail=None,
            )

    def get_territory_balance(self):
        """
        Function returns a map of territory balance
        """


class GenPlannerFuncZonesDTO(GenPlannerDTO):
    profile_scenario: int = Field(..., description="Scenario func zone type")

    @field_validator("profile_scenario", mode="before")
    @classmethod
    def validate_scenario(cls, value: int) -> int:
        if value in [1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13]:
            return int(value)
        raise http_exception(
            400,
            msg="Scenario should be a valid num",
            _input={"scenario": value},
            _detail={"available_values": [1, 2, 3, 4, 5, 6, 7, 8, 10, 11, 12, 13]},
        )


class GenPlannerTerZonesDTO(GenPlannerDTO):
    profile_scenario: int = Field(..., description="Scenario ter zone type")

    @field_validator("profile_scenario", mode="before")
    @staticmethod
    def validate_scenario(value: int):
        if value in [1, 2, 3, 4, 5, 6, 7, 10, 11, 12, 13]:
            return value
        raise http_exception(
            400,
            msg="Scenario should be a valid num",
            _input={"scenario": value},
            _detail={"available_values": [1, 2, 3, 4, 5, 6, 7, 10, 11, 12, 13]},
        )
