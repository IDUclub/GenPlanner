from typing import Self

import geopandas as gpd
from pydantic import BaseModel, Field, model_validator

from app.common.constants.api_constants import scenario_func_zones_map
from app.common.geometries_dto.geometries import PolygonalFeatureCollection


class GenPlannerCustomDTO(BaseModel):
    """
    DTO class for custom renovation response.
    Attributes:
        _
    """

    # service fields
    _territory_gdf: gpd.GeoDataFrame | None = None
    _func_zone = None

    # request params
    profile_id: int = Field(ge=1, le=13, examples=[1], description="Profile ID to generate functional zones")
    territory: PolygonalFeatureCollection = Field(description="Territory to generate functional zones")

    @model_validator(mode="after")
    def validate_territory(self) -> Self:
        """
        Function validator for the territory field and casts it to GeoDataFrame.
        """

        self._territory_gdf = self.territory.as_gdf(4326)
        self._func_zone = scenario_func_zones_map[self.profile_id]
        return self
