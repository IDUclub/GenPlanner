from typing import Literal, Optional, Self

import geopandas as gpd
from genplanner import FunctionalZone, TerritoryZone
from pydantic import BaseModel, Field, model_validator

from app.common.constants.api_constants import scenario_ter_zones_map, name_id_map
from app.common.geometries_dto.geometries import FixZoneFeatureCollection


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
        project_id (int): The project ID.
        scenario_id (int): The scenario ID.
        elevation_angle (Optional[int]): The elevation angle in degrees.
        fix_zones (Optional[FixZoneFeatureCollection]): The fix zone geometry.
        min_block_area (Optional[dict[int, float]): Minimum block area for each generating functional zone.
        functional_zones (Optional[FuncZonesInfoDTO]): The functional zones info to make an amendment on.
        territory_balance (Optional[dict[str, float]]): A dictionary representing the balance of functional zones.
    """

    # service fields
    _custom_id_ter_zone_map = None
    _custom_func_zone = None
    _territory_gdf: gpd.GeoDataFrame | None = None
    _fix_zones_gdf: gpd.GeoDataFrame | None = None
    _initial_zones_to_add: gpd.GeoDataFrame | None = None

    # request params
    project_id: int = Field(examples=[120], description="The project ID")
    scenario_id: int = Field(examples=[835], description="The scenario ID")
    elevation_angle: Optional[int] = Field(
        ge=0,
        le=90,
        default=None,
        examples=[5],
        description="The elevation angle in degrees. All polygons with equal or greater angle are excluded from generation.",
    )
    fix_zones: Optional[FixZoneFeatureCollection] = Field(
        default=None, description="Fixed zone geometry with zone attribute"
    )
    min_block_area: Optional[dict[int, float]] = Field(default={}, description="Map for each ter zone min block area.")
    functional_zones: Optional[FuncZonesInfoDTO] = Field(default=None, description="The functional zones info")
    territory_balance: dict[int, float] = Field(
        description="Balance of functional zones by ID",
        min_length=1,
    )

    @model_validator(mode="after")
    def assign_custom_ter_zone_name(self) -> Self:
        """
        Build custom territorial and functional zone representations from the provided territory
        balance.  In GenPlanner 1.0.0 the `TerritoryZone` constructor expects a zone kind
        (string or `TerritoryZoneKind`) rather than the numeric ID used previously.  We use
        the kind from the default territory zones (`scenario_ter_zones_map`) and apply any
        custom minimum block area if provided.  A `FunctionalZone` is then created from
        these territory zones and the requested ratios.
        """
        id_to_zone: dict[int, TerritoryZone] = {}
        id_to_name: dict[int, str] = {v: k for k, v in name_id_map.items()}

        for k in self.territory_balance.keys():
            key_int = int(k)

            if key_int not in scenario_ter_zones_map:
                continue

            base_zone = scenario_ter_zones_map[key_int]
            min_area = (
                (self.min_block_area or {}).get(key_int)
                if (self.min_block_area or {}).get(key_int) is not None
                else base_zone.min_block_area
            )

            id_to_zone[key_int] = TerritoryZone(
                kind=base_zone.kind,
                name=base_zone.name,
                min_block_area=min_area,
            )

        self._custom_id_ter_zone_map = id_to_zone

        zone_ratio_mapping: dict[TerritoryZone, float] = {}
        for k, ratio in self.territory_balance.items():
            key_int = int(k)
            if key_int in id_to_zone:
                zone_ratio_mapping[id_to_zone[key_int]] = ratio

        self._custom_func_zone = FunctionalZone(zone_ratio_mapping, name="Automatically formed zone")
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
