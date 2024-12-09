import json
from typing import Literal, Any, Optional

import shapely
import shapely.geometry as geom
from pydantic import BaseModel, Field


with open("app/common/example_geometry.json", "r") as et:
    example_territory = json.load(et)


class Geometry(BaseModel):
    """
    Geometry representation for GeoJSON model.
    """

    type: Literal["Polygon", "MultiPolygon"] = Field(examples=[example_territory["type"]])
    coordinates: list[Any] = Field(
        description="list[list[list[int]]] for Polygon",
        examples=[example_territory["coordinates"]],
    )
    _shapely_geom: geom.Polygon | geom.MultiPolygon | None = None

    def as_shapely_geometry(
        self,
    ) -> geom.Polygon | geom.MultiPolygon | geom.LineString:
        """
        Return Shapely geometry object from the parsed geometry.
        """

        if self._shapely_geom is None:
            self._shapely_geom = shapely.from_geojson(json.dumps({"type": self.type, "coordinates": self.coordinates}))
        return self._shapely_geom

    @classmethod
    def from_shapely_geometry(
        cls, geometry: geom.Polygon | geom.MultiPolygon | None
    ) -> Optional["Geometry"]:
        """
        Construct Geometry model from shapely geometry.
        """

        if geometry is None:
            return None
        return cls(**geom.mapping(geometry))
