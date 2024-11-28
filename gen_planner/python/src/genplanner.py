import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import CRS
from rust_optimizer import optimize_space
from shapely.geometry import Point, Polygon, MultiPolygon, LineString
from shapely.ops import polygonize, unary_union
from loguru import logger
from gen_planner.python.src.geom_utils import (
    rotate_coords,
    polygon_angle,
    normalize_coords,
    denormalize_coords,
    generate_points,
)
from gen_planner.python.src.func_zones import FuncZone, Scenario, basic_scenario

poisson_n_radius = {
    2: 0.25,
    3: 0.22,
    4: 0.2,
    5: 0.17,
    6: 0.15,
    7: 0.12,
    8: 0.1,
}


class GenPlanner:
    original_territory: Polygon
    local_crs: CRS
    angle_rad_to_rotate: float
    pivot_point: Point

    def __init__(self, territory: gpd.GeoDataFrame, rotation: bool | float = True):

        self.original_territory = self._gdf_to_poly(territory.copy())

        if rotation:
            coord = self.original_territory.exterior.coords
            self.pivot_point = self.original_territory.centroid
            if isinstance(rotation, float):
                self.angle_rad_to_rotate = np.deg2rad(rotation)
                self.original_territory = Polygon(rotate_coords(coord, self.pivot_point, self.angle_rad_to_rotate))
            else:
                self.angle_rad_to_rotate = polygon_angle(self.original_territory)
                self.original_territory = Polygon(rotate_coords(coord, self.pivot_point, -self.angle_rad_to_rotate))

    def _gdf_to_poly(self, gdf: gpd.GeoDataFrame) -> Polygon:
        self.local_crs = gdf.estimate_utm_crs()
        poly = gdf.to_crs(self.local_crs).union_all()
        if isinstance(poly, Polygon):
            return poly
        elif isinstance(poly, MultiPolygon):
            # TODO deal with multipolygon
            raise RuntimeError

    def zone2block(self, func_zone: FuncZone):
        return zone2block(self.original_territory, func_zone=func_zone, local_crs=self.local_crs)

    def terr2zone2block(self, polygon: Polygon, scenario: Scenario = basic_scenario) -> gpd.GeoDataFrame:
        pass

    def terr2district2zone2block(self, polygon: Polygon, district_areas: list, district_scenarios: list):
        pass

    def run(self):
        # first iteration

        pass


def zone2block(polygon: Polygon, func_zone: FuncZone, local_crs: CRS) -> gpd.GeoDataFrame:
    target_area = polygon.area
    min_area = func_zone.min_block_area
    max_delimeter = 6
    n_blocks = target_area // min_area
    temp_area = min_area
    delimeters = []
    while temp_area < target_area:
        temp_area = temp_area * max_delimeter
        delimeters.append(max_delimeter)
    min_split = 2
    if len(delimeters) == 1:
        min_split = 1
    i = 0
    while temp_area > target_area:
        if delimeters[i] > min_split:
            delimeters[i] = delimeters[i] - 1
        else:
            i += 1
        temp_area = min_area * np.prod(delimeters)
    delimeters[i] = delimeters[i] + 1

    print(f"n_blocks{n_blocks}")
    print(f"delimeters: {delimeters}")

    polygons = [polygon]
    # temp
    result = []
    result.append(polygons)

    for i, nsplit in enumerate(delimeters):
        if i + 1 == len(delimeters):
            to_split = [len(layer) for layer in np.array_split(np.arange(n_blocks), np.prod(delimeters[:-1]))]
        else:
            to_split = [nsplit for _ in polygons]

        print(f"to_split: {to_split}")
        temp_polygons = []

        for n_areas, poly in zip(to_split, polygons):
            areas_dict = {x: 1 / n_areas for x in range(n_areas)}
            print(areas_dict)

            res = _split_polygon(poly, local_crs, areas_dict, point_radius=poisson_n_radius.get(n_areas))
            temp_polygons += res

        polygons = temp_polygons
        result.append(polygons)
    return result
    # return gpd.GeoDataFrame(geometry=polygons, crs=local_crs)


def _split_polygon(
        polygon: Polygon, local_crs, areas_dict: dict, point_radius: float = 0.1, zone_connections=None,
        return_gdf=False
) -> gpd.GeoDataFrame | list[Polygon]:
    if zone_connections is None:
        zone_connections = []
    bounds = polygon.buffer(10).bounds
    normalized_polygon = Polygon(normalize_coords(polygon.buffer(10).exterior.coords, bounds))  # TODO fix shit
    poisson_points = generate_points(normalized_polygon, point_radius)
    logger.debug(f"poisson_points radius: {point_radius}, len: {len(poisson_points)}")
    full_area = normalized_polygon.area
    areas = pd.DataFrame(list(areas_dict.items()), columns=["zone_name", "ratio"])
    areas["ratio"] = areas["ratio"] / areas["ratio"].sum()
    areas["area"] = areas["ratio"] * full_area
    areas.sort_values(by="ratio", ascending=True, inplace=True)
    area_per_site = full_area / (len(poisson_points))
    areas["site_indeed"] = round(areas["area"] / area_per_site).astype(int)
    zones = np.random.permutation(np.repeat(areas.index, areas["site_indeed"]))
    poisson_points = poisson_points[: len(zones)]
    zones = zones[: len(poisson_points)].astype(int)
    normalized_border = [
        round(item, 8)
        for sublist in normalized_polygon.exterior.segmentize(0.1).normalize().coords[::-1]
        for item in sublist
    ]
    for i in range(3):
        try:
            res = optimize_space(
                vtxl2xy=normalized_border,
                site2xy=poisson_points.flatten().round(8).tolist(),
                site2room=zones.tolist(),
                site2xy2flag=[0.0 for _ in range(len(zones) * 2)],
                room2area_trg=areas["area"].sort_index().round(8).tolist(),
                room_connections=zone_connections,
                create_gif=False,
            )
            break
        except RuntimeError as e:
            if i == 2:
                return None

    voronoi_points = res[1]
    new_roads_points = res[0]
    voronoi_sites = res[2]

    voronoi_points = [coords for coords in np.array(voronoi_points).reshape(int(len(voronoi_points) / 2), 2)]

    new_roads = [
        denormalize_coords((voronoi_points[x[0]], voronoi_points[x[1]]), bounds)
        for x in np.array(new_roads_points).reshape(int(len(new_roads_points) / 2), 2)
    ]
    new_roads = [LineString(x) for x in new_roads]

    roads_w_border = new_roads + [LineString(polygon.exterior.coords)]

    devided_zones = gpd.GeoDataFrame(geometry=list(polygonize((unary_union(roads_w_border)))), crs=local_crs)
    centroids = denormalize_coords(
        [coords for coords in np.array(voronoi_sites).reshape(int(len(voronoi_sites) / 2), 2)], bounds
    )
    centroids = gpd.GeoDataFrame(data={"zone": zones}, geometry=[Point(x) for x in centroids], crs=local_crs)
    devided_zones = devided_zones.sjoin(centroids, how="left").groupby("zone").agg({"geometry": "first"}).reset_index()
    devided_zones = devided_zones.merge(areas.reset_index(), left_on="zone", right_on="index").drop(
        columns=["index", "area", "site_indeed"]
    )
    if return_gdf:
        return devided_zones
    else:
        return devided_zones["geometry"].tolist()
