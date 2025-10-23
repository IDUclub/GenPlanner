from typing import Literal, Optional, Self

import geopandas as gpd
from pydantic import BaseModel, Field, model_validator

from app.common.constants.api_constants import scenario_ter_zones_map
from app.common.geometries_dto.geometries import FixZoneFeatureCollection
from app.gen_planner.python.src.zoning.func_zones import FuncZone
from app.gen_planner.python.src.zoning.terr_zones import TerritoryZone


class FuncZonesInfoDTO(BaseModel):

    year: int = Field(examples=[2025], description="Year of functional zones")
    source: Literal["PZZ", "OSM", "User"] = Field(examples=["User"], description="Source of functional zones")
    fixed_functional_zones_ids: list[int] = Field(
        examples=[1619712], description="IDs of functional zones to take into account"
    )


class GenPlannerFuncZonesDTO(BaseModel):
    """
    DTO for functional zones in the GenPlanner service.
    Attributes:
        project_id (Optional[int]): The project ID.
        scenario_id (Optional[int]): The scenario ID.
        fix_zones (Optional[FixZoneFeatureCollection]): The fix zone geometry.
        territory_balance (Optional[dict[str, float]]): A dictionary representing the balance of functional zones.
    """

    # service fields
    _custom_id_ter_zone_map = None
    _custom_func_zone = None
    _territory_gdf: gpd.GeoDataFrame | None = None
    _fix_zones_gdf: gpd.GeoDataFrame | None = None

    # request params
    project_id: int = Field(examples=[120], description="The project ID")
    scenario_id: int = Field(examples=[835], description="The scenario ID")
    elevation_angle: int | None = Field(
        ge=0,
        le=90,
        default=None,
        examples=[5],
        description="The elevation angle in degrees. All polygons with equal or greater angle are excluded from generation.",
    )
    fix_zones: Optional[FixZoneFeatureCollection] = Field(
        default=None, description="Fixed zone geometry with zone attribute"
    )
    min_block_area: Optional[dict[int, float]] = Field(
        default=None, description="Map for each ter zone min block area."
    )
    functional_zones: Optional[FuncZonesInfoDTO] = Field(default=None, description="The functional zones info")
    territory_balance: dict[int, float] = Field(
        description="Balance of functional zones by ID",
    )

    @model_validator(mode="after")
    def assign_custom_ter_zone_name(self) -> Self:

        self._custom_id_ter_zone_map = {
            k: TerritoryZone(
                k,
                self.min_block_area.get(k) if self.min_block_area.get(k) else scenario_ter_zones_map[k].min_block_area,
            )
            for k in self.territory_balance.keys()
        }
        self._custom_func_zone = FuncZone(
            {
                TerritoryZone(
                    k,
                    (
                        self.min_block_area.get(k)
                        if self.min_block_area.get(k)
                        else scenario_ter_zones_map[k].min_block_area
                    ),
                ): v
                for k, v in self.territory_balance.items()
            },
            name="user-defined func zone",
        )
        return self

    @model_validator(mode="after")
    def validate_fixed_zones(self) -> Self:
        """
        Function validates that the fixed zones feature is in the territory_balance and saves as attribute in gdf format.
        """

        if self.fix_zones:
            value_gdf = self.fix_zones.as_gdf()
            value_gdf["fixed_zone"] = value_gdf["fixed_zone"].map(self._custom_id_ter_zone_map)
            self._fix_zones_gdf = value_gdf
        return self
