import json
from pathlib import Path
from typing import Optional, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from app.common.constants.api_constants import custom_ter_zones_map_by_name, scenario_ter_zones_map
from app.common.exceptions.http_exception import http_exception
from app.common.geometries_dto.geometries import FixZoneFeatureCollection, PolygonalFeatureCollection
from app.gen_planner.python.src.zoning.func_zones import FuncZone
from app.gen_planner.python.src.zoning.terr_zones import TerritoryZone

folder_path = Path(__file__).parent.absolute()

with open(folder_path / "examples/territory_balance_example.json") as tbe:
    territory_balance_example = json.load(tbe)


class GenPlannerDTO(BaseModel):
    """
    Base DTO for the GenPlanner service.
    Attributes:
        project_id (Optional[int]): The project ID.
        scenario_id (Optional[int]): The scenario ID.
        territory (Optional[PolygonalFeatureCollection]): The territory geometry.
        fix_zones (Optional[FixZoneFeatureCollection]): The fix zone geometry.
    """

    project_id: Optional[int] = Field(default=None, examples=[72], description="The project ID")
    scenario_id: Optional[int] = Field(default=None, examples=[72], description="The scenario ID")
    profile_scenario: int = Field(..., description="Scenario func zone type")
    territory: Optional[PolygonalFeatureCollection] = Field(default=None, description="The territory geometry")
    fix_zones: Optional[FixZoneFeatureCollection] = Field(default=None, description="The fix zone geometry")

    @model_validator(mode="after")
    def validate_territory(self) -> Self:
        """
        Functon validates that either a geojson territory or a project ID is provided.
        """

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
        return self


class GenPlannerFuncZonesDTO(GenPlannerDTO):
    """
    DTO for functional zones in the GenPlanner service.
    Attributes:
        territory_balance (Optional[dict[str, float]]): A dictionary representing the balance of functional zones.
        profile_scenario (int): The scenario type for functional zones.
    """

    profile_scenario: Optional[int] = Field(default=None, description="Scenario func zone type")
    territory_balance: Optional[dict[str | int, float]] = Field(
        default=None,
        examples=territory_balance_example,
    )

    @field_validator("territory_balance")
    @classmethod
    def validate_territory_balance(cls, value: Optional[dict[str | int, float]]) -> dict[str | int, float] | None:
        """
        Function validates that the territory balance is a dict with string or int keys and float values.
        Args:
            value ([dict[str | int, float]]): The territory balance to validate.
        Returns:
            [dict[str | int, float]]: The validated territory balance.
        """

        if value is not None:
            value = {(int(k) if k.isnumeric() else k): v for k, v in value.items()}
            if (keys_set := set(value.keys())).issubset(set(custom_ter_zones_map_by_name.keys())):
                return value
            elif keys_set.issubset(set(scenario_ter_zones_map.keys())):
                return value
            else:
                raise http_exception(
                    400,
                    "Territories zones are not supported",
                    _input=keys_set,
                    _detail={
                        "available_values": {
                            "str_values": list(custom_ter_zones_map_by_name.keys()),
                            "int_values": list(scenario_ter_zones_map.keys()),
                        }
                    },
                )

    @model_validator(mode="after")
    def validate_profile_scenario(self) -> Self:
        """
        Function validates that the profile scenario is a valid scenario.
        """

        if self.profile_scenario and self.territory_balance:
            raise http_exception(
                400,
                msg="Can pass either profile_scenario or territory_balance (strict or)",
                _input={
                    "profile_scenario": self.profile_scenario,
                    "territory_balance": self.territory_balance,
                },
                _detail={},
            )
        elif not self.profile_scenario and not self.territory_balance:
            raise http_exception(
                400,
                msg="Have to pass either profile_scenario or territory_balance (strict or)",
                _input={
                    "profile_scenario": self.profile_scenario,
                    "territory_balance": self.territory_balance,
                },
                _detail={},
            )
        return self

    @model_validator(mode="after")
    def validate_ter_balance_fix_zones(self) -> Self:
        """
        Function checks weather all zones in territory_balance matches fixed zones
        """

        fix_zones = self.fix_zones.as_gdf()
        fixed_zones = set(i for i in fix_zones["fixed_zone"].unique())
        balanced_zones = set(self.territory_balance.keys())
        if fixed_zones.difference(balanced_zones):
            raise http_exception(
                400,
                "fixed_zones properties should match all balance zones and be the same type",
                _input={"fixed_zones": list(fixed_zones), "balance_zones": list(balanced_zones)},
                _detail=None,
            )
        return self

    @model_validator(mode="after")
    def validate_fixed_zones(self) -> Self:
        """
        Function validates that the fixed zones feature is in the territory_balance.
        """

        value_gdf = self.fix_zones.as_gdf()
        func_zone = self.get_territory_balance()
        value_gdf["fixed_zone"] = value_gdf["fixed_zone"].map({k.name: k for k in func_zone.zones_ratio.keys()})
        self.fix_zones = FixZoneFeatureCollection(**value_gdf.to_geo_dict())
        return self

    def get_territory_balance(self) -> FuncZone:
        """
        Function returns a FuncZone object based on the territory balance.
        Returns:
            FuncZone: A FuncZone object representing the territory balance.
        """

        if set(self.territory_balance.keys()).issubset(set(custom_ter_zones_map_by_name.keys())):
            return FuncZone(
                # TODO replace with map
                {TerritoryZone(k): v for k, v in self.territory_balance.items()},
                name="user-defined func zone",
            )
        else:
            return FuncZone(
                {scenario_ter_zones_map[k]: v for k, v in self.territory_balance.items()},
                name="user-defined func zone",
            )


class GenPlannerTerZonesDTO(GenPlannerDTO):

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
