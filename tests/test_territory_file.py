import io
import json
import zipfile

import geopandas as gpd
import pytest
from fastapi import HTTPException
from shapely.geometry import LineString, Polygon

from app.common.geometries_dto import territory_file as territory_file_module
from app.common.geometries_dto.territory_file import parse_territory_file

_SQUARE = Polygon([(30.0, 59.0), (30.1, 59.0), (30.1, 59.1), (30.0, 59.1), (30.0, 59.0)])


def _upload(content: bytes, filename: str):
    from starlette.datastructures import UploadFile

    return UploadFile(file=io.BytesIO(content), filename=filename)


def _geojson_bytes(gdf: gpd.GeoDataFrame) -> bytes:
    return gdf.to_json().encode("utf-8")


def _shapefile_zip_bytes(gdf: gpd.GeoDataFrame, tmp_path) -> bytes:
    shp_dir = tmp_path / "shp"
    shp_dir.mkdir()
    shp_path = shp_dir / "territory.shp"
    gdf.to_file(shp_path)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for part in shp_dir.iterdir():
            zf.write(part, arcname=part.name)
    return buffer.getvalue()


_KML_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
              30.0,59.0,0 30.1,59.0,0 30.1,59.1,0 30.0,59.1,0 30.0,59.0,0
            </coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
  </Document>
</kml>
"""


@pytest.mark.asyncio
async def test_valid_geojson_without_crs_is_treated_as_4326():
    gdf = gpd.GeoDataFrame({"geometry": [_SQUARE]}, crs=4326)
    upload = _upload(_geojson_bytes(gdf), "territory.geojson")

    result = await parse_territory_file(upload)

    assert len(result.features) == 1
    assert result.features[0].geometry.type == "Polygon"


@pytest.mark.asyncio
async def test_geojson_with_non_4326_crs_gets_reprojected():
    gdf = gpd.GeoDataFrame({"geometry": [_SQUARE]}, crs=4326).to_crs(3857)
    upload = _upload(_geojson_bytes(gdf), "territory.geojson")

    result = await parse_territory_file(upload)

    lon, lat = result.features[0].geometry.coordinates[0][0]
    assert -180 <= lon <= 180
    assert -90 <= lat <= 90


@pytest.mark.asyncio
async def test_unsupported_extension_is_rejected():
    upload = _upload(b"not-a-real-file", "territory.txt")

    with pytest.raises(HTTPException) as exc_info:
        await parse_territory_file(upload)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_empty_file_is_rejected():
    upload = _upload(b"", "territory.geojson")

    with pytest.raises(HTTPException) as exc_info:
        await parse_territory_file(upload)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_oversized_file_is_rejected(monkeypatch):
    monkeypatch.setattr(territory_file_module, "MAX_TERRITORY_FILE_SIZE_BYTES", 10)
    gdf = gpd.GeoDataFrame({"geometry": [_SQUARE]}, crs=4326)
    upload = _upload(_geojson_bytes(gdf), "territory.geojson")

    with pytest.raises(HTTPException) as exc_info:
        await parse_territory_file(upload)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_non_polygon_geometry_is_rejected():
    gdf = gpd.GeoDataFrame({"geometry": [LineString([(30.0, 59.0), (30.1, 59.1)])]}, crs=4326)
    upload = _upload(_geojson_bytes(gdf), "territory.geojson")

    with pytest.raises(HTTPException) as exc_info:
        await parse_territory_file(upload)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_malformed_file_is_rejected():
    upload = _upload(b"{not valid geojson", "territory.geojson")

    with pytest.raises(HTTPException) as exc_info:
        await parse_territory_file(upload)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_valid_shapefile_zip_is_parsed(tmp_path):
    gdf = gpd.GeoDataFrame({"geometry": [_SQUARE]}, crs=4326)
    upload = _upload(_shapefile_zip_bytes(gdf, tmp_path), "territory.zip")

    result = await parse_territory_file(upload)

    assert len(result.features) == 1
    assert result.features[0].geometry.type == "Polygon"


@pytest.mark.asyncio
async def test_valid_kml_is_parsed():
    upload = _upload(_KML_TEMPLATE.encode("utf-8"), "territory.kml")

    result = await parse_territory_file(upload)

    assert len(result.features) == 1
    assert result.features[0].geometry.type == "Polygon"


@pytest.mark.asyncio
async def test_result_round_trips_through_polygonal_feature_collection_as_gdf():
    gdf = gpd.GeoDataFrame({"geometry": [_SQUARE]}, crs=4326)
    upload = _upload(_geojson_bytes(gdf), "territory.geojson")

    result = await parse_territory_file(upload)
    result_gdf = result.as_gdf(4326)

    assert not result_gdf.empty
    assert json.loads(result_gdf.to_json())["features"][0]["geometry"]["type"] == "Polygon"
