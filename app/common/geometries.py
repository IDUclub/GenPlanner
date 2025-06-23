import json
from typing import Literal, Any, Optional, Self

import shapely
import shapely.geometry as geom
from mercantile import feature
from pydantic import BaseModel, Field, model_validator, field_validator

from app.common.exceptions.http_exception import http_exception


with open("app/common/example_geometry.json", "r") as et:
    polygon_example_territory = json.load(et)

with open("app/common/fixed_points_example.json", "r") as fpe:
    fixed_points_example = json.load(fpe)


class Geometry(BaseModel):
    """
    Geometry representation for GeoJSON model.
    """

    type: Literal["Polygon", "MultiPolygon"] = Field(examples=[polygon_example_territory["type"]])
    coordinates: list[Any] = Field(
        description="list[list[list[int]]] for Polygon",
        examples=[polygon_example_territory["coordinates"]],
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


class PointGeometry(BaseModel):
    """
    Geometry representation for Point as dict
    """

    type: Literal["Point"] = Field(examples=[fixed_points_example["features"][0]["geometry"]["type"]])
    coordinates: list[Any] = Field(
        description="list[int] for Point",
        examples=[fixed_points_example["features"][0]["geometry"]["coordinates"]]
    )

    @model_validator(mode="after")
    def validate_geom(self) -> Self:
        """
        Validating that the geometry dict is valid
        """

        counter = 0
        check = self.coordinates.copy()
        while type(check) is list:
            check = check[0]
            counter += 1
        if counter != 1:
            raise http_exception(
                status_code=400,
                msg="Input should be a valid Point",
                _input=self.coordinates,
                _detail={"nesting": counter},
            )
        return self

    def as_dict(self) -> dict:
        return self.__dict__


class PolygonalGeometry(BaseModel):
    """
    Geometry representation for Polygon as dict
    """

    type: Literal["Polygon", "MultiPolygon"] = Field(examples=[polygon_example_territory["type"]])
    coordinates: list[Any] = Field(
        description="list[list[list[float]]] for Polygon",
        examples=[polygon_example_territory["coordinates"]],
    )

    @model_validator(mode="after")
    def validate_geom(self) -> Self:
        """
        Validating that the geometry dict is valid
        """

        counter = 0
        check = self.coordinates.copy()
        while type(check) is list:
            check = check[0]
            counter += 1
        if counter not in (3, 4):
            raise http_exception(
                status_code=400,
                msg="Input should be a valid Polygon or MultiPolygon",
                _input=self.coordinates,
                _detail={"nesting": counter},
            )

        return self

    def as_dict(self) -> dict:
        return self.__dict__


class PolygonalFeature(BaseModel):
    type: Literal["Feature"] = Field(examples=["Feature"])
    id: Optional[int] = Field(default=None, examples=[0])
    geometry: PolygonalGeometry
    properties: dict[str, Any] = Field(default=None, examples=[{"params": 1}])

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "geometry": self.geometry.as_dict(),
            "properties": self.properties,
        }


class PointFeature(BaseModel):
    type: Literal["Feature"] = Field(examples=["Feature"])
    id: Optional[int] = Field(default=None, examples=[0])
    geometry: PointGeometry
    properties: dict[str, Any] = Field(default=None, examples=[{"fixed_zone": "Territory zone \"transport\""}])

    @field_validator("properties", mode="after")
    @classmethod
    def validate_properties(cls, value: dict[str, Any]) -> dict[str, Any]:
        if "fixed_zone" not in value:
            raise http_exception(
                status_code=400,
                msg="Input should contain f 'fixed_zone' property'",
                _detail={},
                _input=value,
            )
        return value

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "geometry": self.geometry.as_dict(),
            "properties": self.properties,
        }


class PolygonalFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = Field(examples=["FeatureCollection"])
    features: list[PolygonalFeature] = Field(...)

    def as_geo_dict(self):
        """
        Construct FeatureCollection dict
        """

        return {
            "type": self.type,
            "features": [feature.as_dict() for feature in self.features],
        }


class PointFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = Field(examples=["FeatureCollection"])
    features: list[PointFeature] = Field(...)

    def as_geo_dict(self):
        """
        Construct FeatureCollection with only points geometry
        """

        return {
            "type": self.type,
            "features": [feature.as_dict() for feature in self.features],
        }
