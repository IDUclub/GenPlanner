from typing import Self

import geopandas as gpd
from genplanner import FunctionalZone
from pydantic import BaseModel, Field, model_validator

from app.common.constants.api_constants import scenario_func_zones_map
from app.common.geometries_dto.geometries import PolygonalFeatureCollection


class GenPlannerCustomDTO(BaseModel):
    """
    DTO class for custom renovation response.
    Attributes:
        profile_id (int): Profile ID to generate functional zones on
        territory (PolygonalFeatureCollection | None): territory to generate functional zones on

        _territory_gdf (gpd.GeoDataFrame | None): gpd.GeoDataFrame representation of the requested territory
        _func_zone (FunctionalZone | None): custom functional zones representation to generate functional zones on
    """

    # service fields
    _territory_gdf: gpd.GeoDataFrame | None = None
    _func_zone: FunctionalZone | None = None

    # request params
    profile_id: int = Field(examples=[1], description="Profile ID to generate functional zones")
    territory: PolygonalFeatureCollection = Field(description="Territory to generate functional zones")

    @model_validator(mode="after")
    def validate_territory(self) -> Self:
        """
        Function validator for the territory field and casts it to GeoDataFrame.
        """

        if self.profile_id not in scenario_func_zones_map:
            raise ValueError(f"Unknown profile_id {self.profile_id}, available: {sorted(scenario_func_zones_map)}")

        self._territory_gdf = self.territory.as_gdf(4326)
        self._func_zone = scenario_func_zones_map[self.profile_id]
        return self
