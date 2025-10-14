import math

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.stats.qmc import PoissonDisk
from shapely import GeometryCollection, LineString, MultiLineString, MultiPolygon, Point, Polygon
from shapely.ops import nearest_points, polygonize, unary_union


def rotate_poly(poly: Polygon | MultiPolygon, pivot_point, angle_rad) -> Polygon | MultiPolygon:
    if isinstance(poly, Polygon):
        return Polygon(rotate_coords(poly.exterior.coords, pivot_point, angle_rad))
    return MultiPolygon([Polygon(rotate_coords(geom.exterior.coords, pivot_point, angle_rad)) for geom in poly.geoms])


def elastic_wrap(gdf: gpd.GeoDataFrame) -> Polygon:
    gdf = gdf.copy()
    multip = gpd.GeoDataFrame(geometry=[gdf.union_all()], crs=gdf.crs).explode(ignore_index=True)
    max_dist = (
        np.ceil(multip.apply(lambda row: multip.drop(row.name).distance(row.geometry).min(), axis=1).max(axis=0)) + 0.1
    )
    if pd.isna(max_dist):
        max_dist = 1
    poly = multip.buffer(max_dist + 1).union_all().buffer(-max_dist)
    if isinstance(poly, MultiPolygon):
        return elastic_wrap(gpd.GeoDataFrame(geometry=[poly], crs=gdf.crs))
    poly = Polygon(poly.exterior)
    return poly


def rotate_coords(coords: list, pivot: Point, angle_rad: float) -> list[tuple[float, float]]:
    px, py = pivot.x, pivot.y
    rotated_coords = []
    for x, y in coords:
        translated_x = x - px
        translated_y = y - py

        rotated_x = translated_x * math.cos(angle_rad) - translated_y * math.sin(angle_rad)
        rotated_y = translated_x * math.sin(angle_rad) + translated_y * math.cos(angle_rad)

        final_x = rotated_x + px
        final_y = rotated_y + py
        rotated_coords.append((final_x, final_y))
    return rotated_coords


def polygon_angle(rect: Polygon) -> float:
    rect = rect.minimum_rotated_rectangle
    if not isinstance(rect, Polygon):
        return 0
    coords = list(rect.exterior.coords)[:-1]
    sides = [(coords[0], coords[1]), (coords[1], coords[2])]

    lengths = [math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2) for (x1, y1), (x2, y2) in sides]
    long_side_idx = lengths.index(max(lengths))
    long_side = sides[long_side_idx]

    (x1, y1), (x2, y2) = long_side
    angle_rad = math.atan2(y2 - y1, x2 - x1)
    return angle_rad


def normalize_coords(coords: list[tuple[float, float]], bounds: tuple):
    minx, miny, maxx, maxy = bounds
    width = maxx - minx
    height = maxy - miny
    scale = max(width, height)
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    normalized_coords = [((x - cx) / scale + 0.5, (y - cy) / scale + 0.5) for x, y in coords]
    return normalized_coords


def denormalize_coords(normalized_coords: list[tuple[float, float]], bounds: tuple):
    minx, miny, maxx, maxy = bounds
    width = maxx - minx
    height = maxy - miny
    scale = max(width, height)
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    denormalized_coords = [((x - 0.5) * scale + cx, (y - 0.5) * scale + cy) for x, y in normalized_coords]

    return denormalized_coords


def generate_points(area_to_fill: Polygon, radius):
    bbox = area_to_fill.envelope
    min_x, min_y, max_x, max_y = bbox.bounds
    width = max_x - min_x
    height = max_y - min_y
    norm_radius = radius / max(width, height)
    engine = PoissonDisk(d=2, radius=norm_radius)
    points = engine.random(int((1 // (math.pi * radius**2)) * bbox.area * 10))
    points_in_polygon = np.array([point for point in points])
    return points_in_polygon


def geometry_to_multilinestring(geom):
    def convert_polygon(polygon: Polygon):
        lines = []
        exterior = LineString(polygon.exterior.coords)
        lines.append(exterior)
        interior = [LineString(p.coords) for p in polygon.interiors]
        lines = lines + interior
        return lines

    def convert_multipolygon(polygon: MultiPolygon):
        return MultiLineString(sum([convert_polygon(p) for p in polygon.geoms], []))

    if geom.geom_type == "Polygon":
        return MultiLineString(convert_polygon(geom))
    if geom.geom_type == "MultiPolygon":
        return convert_multipolygon(geom)
    if geom.geom_type in ["MultiLineString", "LineString"]:
        return geom
    return LineString()


def explode_linestring(geometry: LineString) -> list[LineString]:
    """A function to return all segments of a linestring as a list of linestrings"""
    coords_ext = geometry.coords  # Create a list of all line node coordinates
    result = [LineString(part) for part in zip(coords_ext, coords_ext[1:])]
    return result


def territory_splitter(
    gdf_to_split: gpd.GeoDataFrame,
    splitters: gpd.GeoDataFrame | list[gpd.GeoDataFrame],
    return_splitters=False,
    reproject_attr=False,
) -> gpd.GeoDataFrame:

    original_crs = gdf_to_split.crs
    local_crs = gdf_to_split.estimate_utm_crs()
    gdf_to_split = gdf_to_split.to_crs(local_crs)
    if isinstance(splitters, list):
        splitters = pd.concat(splitters, ignore_index=True)
    splitters = splitters.to_crs(local_crs)
    lines_orig = gdf_to_split.geometry.apply(geometry_to_multilinestring).to_list()
    lines_splitters = splitters.geometry.apply(geometry_to_multilinestring).to_list()
    polygons = (
        gpd.GeoDataFrame(geometry=list(polygonize(unary_union(lines_orig + lines_splitters))), crs=local_crs)
        .clip(gdf_to_split.to_crs(local_crs), keep_geom_type=True)
        .explode()
    )

    polygons_points = polygons.copy()
    polygons_points.geometry = polygons.representative_point()
    joined_ind = polygons_points.sjoin(splitters, how="inner", predicate="within").index.tolist()
    polygons["is_splitter"] = polygons.index.isin(joined_ind)

    # polygons.geometry = polygons.apply(
    #     lambda x: Polygon(x.geometry.exterior) if not x["is_splitter"] else x.geometry, axis=1
    # )
    # non_splitters = polygons[~polygons["is_splitter"]]
    # contains = non_splitters.sjoin(non_splitters, predicate="contains")
    # to_kick = contains[~(contains.index == contains["index_right"])]["index_right"].to_list()
    # polygons.drop(index=to_kick, inplace=True)

    polygons = polygons[polygons.area >= 1]

    if reproject_attr:
        attrs_joined = polygons_points.loc[polygons.index].sjoin(gdf_to_split, how="left", predicate="within")
        cols_left = set(polygons_points.columns)
        cols_to_add = [c for c in attrs_joined.columns if c not in cols_left and c != "index_right"]
        if cols_to_add:
            polygons = polygons.join(attrs_joined[cols_to_add])

    if not return_splitters:
        return polygons[~polygons["is_splitter"]].to_crs(original_crs).drop(columns=["is_splitter"])

    return polygons.to_crs(original_crs)


def patch_polygon_interior(polygon: Polygon) -> Polygon:
    inner_geoms = [Polygon(ring) for ring in polygon.interiors]
    while len(inner_geoms) > 0:
        lines = []
        for i in range(len(inner_geoms)):
            all_but_cur = inner_geoms.copy()
            poly = all_but_cur.pop(i)
            lines.append(
                LineString(nearest_points(poly, GeometryCollection(all_but_cur + [polygon.exterior])))
                .buffer(0.01, resolution=1)
                .exterior
            )

        polygons = list(polygonize(unary_union([geometry_to_multilinestring(polygon)] + lines)))
        repr_point = polygon.representative_point()
        for poly in polygons:
            if poly.contains(repr_point):
                polygon = poly
                break
        inner_geoms = [Polygon(ring) for ring in polygon.interiors]
    return polygon


def extend_linestring(line: LineString, distance: float = 1.0) -> LineString:
    if len(line.coords) < 2:
        raise ValueError("LineString must have at least two points.")

    x0, y0 = line.coords[0]
    x1, y1 = line.coords[1]
    dx_start = x0 - x1
    dy_start = y0 - y1
    length_start = math.hypot(dx_start, dy_start)
    unit_dx_start = dx_start / length_start
    unit_dy_start = dy_start / length_start
    new_start = (x0 + unit_dx_start * distance, y0 + unit_dy_start * distance)

    xN_1, yN_1 = line.coords[-2]
    xN, yN = line.coords[-1]
    dx_end = xN - xN_1
    dy_end = yN - yN_1
    length_end = math.hypot(dx_end, dy_end)
    unit_dx_end = dx_end / length_end
    unit_dy_end = dy_end / length_end
    new_end = (xN + unit_dx_end * distance, yN + unit_dy_end * distance)

    new_coords = [new_start] + list(line.coords[1:-1]) + [new_end]
    return LineString(new_coords)
