import json
from pathlib import Path
from typing import Any, Literal, Optional, Self

import shapely
import shapely.geometry as geom
from pydantic import BaseModel, Field, field_validator, model_validator

from app.common.constants.api_constants import custom_ter_zones_map_by_name, scenario_func_zones_map
from app.common.exceptions.http_exception import http_exception

folder_path = Path(__file__).parent.absolute()


with open(folder_path / "example_geometry.json", "r") as et:
    polygon_example_territory = json.load(et)

with open(folder_path / "fixed_points_example.json", "r") as fpe:
    fixed_points_example = json.load(fpe)

with open(folder_path / "linestring_geometry.json", "r") as lg:
    linestring_geom = json.load(lg)

fixed_zones_name = []


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
    def from_shapely_geometry(cls, geometry: geom.Polygon | geom.MultiPolygon | None) -> Optional["Geometry"]:
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
        description="list[int] for Point", examples=[fixed_points_example["features"][0]["geometry"]["coordinates"]]
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


class LinerGeometry(BaseModel):
    """
    Geometry representation for Lines as dict
    """

    type: Literal["LineString", "MultiLineString"] = Field(examples=["LineString", "MultiLineString"])
    coordinates: list[Any] = Field(description="list[list[list[float]]] for Polygon", examples=[linestring_geom])

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
        if counter not in (2, 3):
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


class LineStringFeature(BaseModel):
    type: Literal["Feature"] = Field(examples=["Feature"])
    id: Optional[int] = Field(default=None, examples=[0])
    geometry: LinerGeometry
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
    properties: dict[str, Any] = Field(default=None, examples=[{"fixed_zone": 'Territory zone "transport"'}])

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

        if value["fixed_zone"] not in [
            list(custom_ter_zones_map_by_name.keys()) + list(scenario_func_zones_map.keys())
        ]:
            raise http_exception(
                400,
                msg="Input f 'fixed_zone' property is not valid",
                _input=value,
                _detail={
                    "str": {"available_fixed_zones_names": list(custom_ter_zones_map_by_name.keys())},
                    "int": {"available_fixed_zones_ids": list(scenario_func_zones_map.keys())},
                },
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
