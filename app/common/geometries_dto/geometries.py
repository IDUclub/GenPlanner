import json
from pathlib import Path
from typing import Any, Literal, Optional, Self

import geopandas as gpd
from pydantic import BaseModel, Field, field_validator
from pyproj import CRS
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from app.common.constants.api_constants import custom_ter_zones_map_by_name, scenario_func_zones_map
from app.common.exceptions.http_exception import http_exception

folder_path = Path(__file__).parent.absolute()
geom_types = ["Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon"]


with open(folder_path / "example_geometry.json", "r") as et:
    polygon_example_territory = json.load(et)

with open(folder_path / "fixed_points_example.json", "r") as fpe:
    fixed_points_example = json.load(fpe)

with open(folder_path / "linestring_geometry.json", "r") as lg:
    linestring_geom = json.load(lg)

fixed_zones_name = []


class BaseGeomModel(BaseModel):

    def as_dict(self):
        return self.model_dump()


class Geometry(BaseGeomModel):
    """
    Geometry representation for GeoJSON model.
    """

    type: Literal["Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon"] = Field(
        examples=[polygon_example_territory["type"]]
    )
    coordinates: list[Any] = Field(
        description="list[float | list] for Geometry in geojson notation",
        examples=[polygon_example_territory["coordinates"]],
    )

    @staticmethod
    def validate_geom(coordinates: list[Any], enclosure: int | list | tuple) -> list[Any]:
        """
        Validating that the geometry dict is valid for provided enclosure level.
        Args:
            coordinates (list[Any]): Coordinates of the geometry.
            enclosure (int | list | tuple): Expected level of nesting for the coordinates.
        Returns:
            None
        Raises:
            400, if the coordinates do not match the expected level of nesting.
        """

        counter = 0
        check = coordinates.copy()
        while type(check) is list:
            check = check[0]
            counter += 1
        if counter != 1:
            raise http_exception(
                status_code=400,
                msg="Input should be a valid Point",
                _input=coordinates,
                _detail={"nesting": counter},
            )
        return coordinates

    @field_validator("coordinates", mode="after")
    @classmethod
    def validate_coordinates(cls, value: list[Any]) -> list[Any]:
        """
        Validating that the coordinates are valid for the geometry type.
        Args:
            value (list[Any]): Coordinates of the geometry.
        Returns:
            list[Any]: Validated coordinates.
        Raises:
            400, if the coordinates do not match the expected level of nesting.
        """

        match cls.type:
            case "Point":
                return cls.validate_geom(value, enclosure=1)
            case "MultiPoint" | "LineString":
                return cls.validate_geom(value, enclosure=2)
            case "MultiLineString" | "Polygon":
                return cls.validate_geom(value, enclosure=3)
            case "MultiPolygon":
                return cls.validate_geom(value, enclosure=4)
            case _:
                raise http_exception(
                    400,
                    "Input should be a valid Geometry type",
                    _input=value,
                    _detail={"available_types": geom_types},
                )

    def as_geom(self) -> BaseGeometry:
        return shape(self.model_dump())


class SimplePointGeometry(Geometry):
    """
    Geometry representation for Point as dict
    """

    type: Literal["Point"] = Field(examples=[fixed_points_example["features"][0]["geometry"]["type"]])


class LinerGeometry(Geometry):
    """
    Geometry representation for Lines as dict
    """

    type: Literal["LineString", "MultiLineString"] = Field(examples=["LineString", "MultiLineString"])


class PolygonalGeometry(Geometry):
    """
    Geometry representation for Polygon as dict
    """

    type: Literal["Polygon", "MultiPolygon"] = Field(examples=[polygon_example_territory["type"]])


class Feature(BaseGeomModel):
    type: Literal["Feature"] = Field(examples=["Feature"])
    bbox: Optional[list[float]] = Field(
        default=None, examples=[[100.0, 0.0, 105.0, 1.0]], description="Bounding box for geometry"
    )
    geometry: Geometry
    properties: dict[str, Any] = Field(default=None, examples=[{"params": 1}], description="Properties for geometry")
    id: Optional[int] = Field(default=None, examples=[0])

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "bbox": self.bbox,
            "geometry": self.geometry.as_dict(),
            "properties": self.properties,
        }


class FixZonePointFeature(Feature):

    geometry: SimplePointGeometry

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


class LineStringFeature(BaseModel):

    geometry: LinerGeometry


class PolygonalFeature(BaseModel):

    geometry: PolygonalGeometry


class NamedCRS(BaseModel):
    """
    Named crs
    """

    name: Optional[str] = Field(examples=["urn:ogc:def:crs:OGC:1.3:CRS84"], description="Name of CRS")

    def as_dict(self) -> dict:
        return self.model_dump()


class LinkedCRS(BaseGeomModel):
    """
    Linked crs
    """

    href: Optional[str] = Field(examples=["http://example.com/crs/42"], description="Href of CRS")
    type: Optional[str] = Field(examples=["proj4"], description="Type of CRS, e.g. proj4, wkt, etc.")


class FeatureCollectionCRS(BaseGeomModel):
    """
    Properties for CRS
    """

    type: Literal["name", "link"] = Field(examples=["name", "link"], description="Type of CRS")
    properties: NamedCRS | LinkedCRS

    def as_dict(self):
        return {"type": self.type, "properties": self.properties}

    def as_py_proj_crs(self) -> CRS:
        """
        Convert FeatureCollectionCRS to pyproj.CRS object
        """
        return CRS.from_user_input(self.as_dict())


class FeatureCollection(BaseGeomModel):

    type: Literal["FeatureCollection"] = Field(examples=["FeatureCollection"])
    bbox: Optional[list[float]] = Field(
        examples=[[100.0, 0.0, 105.0, 1.0]], description="Bounding box for geometry collection"
    )
    features: list[Feature]
    crs: Optional[FeatureCollectionCRS]

    def as_dict(self) -> dict:
        return {
            "type": self.type,
            "bbox": self.bbox,
            "features": [feature.as_dict() for feature in self.features],
            "crs": self.crs.as_dict(),
        }

    def as_gdf(self, crs: int | str | CRS | None = 4326) -> gpd.GeoDataFrame:
        """
        Function forms FeatureCollection to a GeoDataFrame.
        If crs is not included in FeatureCollection,
        it'll will be extracted from external or set to EPSG:4326 by default.
        Args:
            crs (int | str | CRS | None): Coordinate Reference System to set for GeoDataFrame. Default to 4326
        Returns:
            gpd.GeoDataFrame: GeoDataFrame representation of the FeatureCollection.
        """

        if self.crs:
            return gpd.GeoDataFrame.from_features(self.as_dict())
        return gpd.GeoDataFrame.from_features(self.as_dict(), crs=crs)


class FixZoneFeatureCollection(BaseModel):

    features: list[FixZonePointFeature]


class LineStringFeatureCollection(BaseModel):

    features: list[LineStringFeature]


class PolygonalFeatureCollection(BaseModel):

    features: list[PolygonalFeature]
