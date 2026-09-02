import json
import os
import tempfile
from pathlib import Path

import geopandas as gpd
from fastapi import UploadFile
from loguru import logger

from app.common.exceptions.http_exception import http_exception

from .geometries import PolygonalFeatureCollection

MAX_TERRITORY_FILE_SIZE_BYTES = 15 * 1024 * 1024

_SUPPORTED_EXTENSIONS = {".geojson", ".json", ".zip", ".kml"}
_POLYGONAL_GEOM_TYPES = {"Polygon", "MultiPolygon"}


async def parse_territory_file(upload: UploadFile) -> PolygonalFeatureCollection:
    """
    Read an uploaded territory boundary file (GeoJSON, zipped Shapefile, or KML) and
    return it as a PolygonalFeatureCollection in EPSG:4326.

    Reprojects to 4326 when the file carries a CRS; assumes the file is already in 4326
    when it doesn't (GeoJSON without a legacy `crs` member already defaults to this per
    RFC 7946, and KML is always WGS84 by spec, so this only matters for Shapefiles
    missing a .prj).
    """

    filename = upload.filename or ""
    extension = Path(filename).suffix.lower()
    if extension not in _SUPPORTED_EXTENSIONS:
        raise http_exception(
            400,
            "Unsupported territory file format",
            _input={"filename": filename},
            _detail={"supported_extensions": sorted(_SUPPORTED_EXTENSIONS)},
        )

    content = await upload.read()
    if not content:
        raise http_exception(400, "Territory file is empty", _input={"filename": filename}, _detail={})
    if len(content) > MAX_TERRITORY_FILE_SIZE_BYTES:
        raise http_exception(
            400,
            "Territory file is too large",
            _input={"filename": filename, "size_bytes": len(content)},
            _detail={"max_size_bytes": MAX_TERRITORY_FILE_SIZE_BYTES},
        )

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=extension, delete=False) as tmp_file:
            tmp_file.write(content)
            tmp_path = tmp_file.name

        source = f"zip://{tmp_path}" if extension == ".zip" else tmp_path
        try:
            gdf = gpd.read_file(source)
        except Exception as exc:
            logger.warning(f"Failed to read territory file {filename}: {exc}")
            raise http_exception(
                400,
                "Could not read territory file",
                _input={"filename": filename},
                _detail={"error": str(exc)},
            ) from exc
    finally:
        if tmp_path is not None:
            os.unlink(tmp_path)

    if gdf.empty:
        raise http_exception(400, "Territory file contains no features", _input={"filename": filename}, _detail={})

    if gdf.crs is None:
        gdf = gdf.set_crs(4326)
    else:
        gdf = gdf.to_crs(4326)

    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
    gdf = gdf[gdf.geometry.geom_type.isin(_POLYGONAL_GEOM_TYPES)]

    if gdf.empty:
        raise http_exception(
            400,
            "Territory file contains no polygon geometry",
            _input={"filename": filename},
            _detail={"allowed_geometry_types": sorted(_POLYGONAL_GEOM_TYPES)},
        )

    geojson_dict = json.loads(gdf.to_json())
    try:
        return PolygonalFeatureCollection.model_validate(geojson_dict)
    except Exception as exc:
        logger.warning(f"Territory file {filename} did not validate as a polygonal feature collection: {exc}")
        raise http_exception(
            400,
            "Territory file could not be converted to a valid polygonal boundary",
            _input={"filename": filename},
            _detail={"error": str(exc)},
        ) from exc
