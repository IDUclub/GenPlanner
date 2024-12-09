import concurrent.futures
import multiprocessing

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import CRS
from rust_optimizer import optimize_space
from shapely.geometry import Point, Polygon, MultiPolygon, LineString

from app.gen_planner.python.src.zoning import TerritoryZone, FuncZone, basic_scenario, gen_plan, GenPlan
from app.gen_planner.python.src.geom_utils import (
    rotate_coords,
    polygon_angle,
    normalize_coords,
    denormalize_coords,
    generate_points,
)

poisson_n_radius = {
    2: 0.25,
    3: 0.23,
    4: 0.22,
    5: 0.2,
    6: 0.17,
    7: 0.15,
    8: 0.1,
}


class GenPlanner:
    original_territory: Polygon
    local_crs: CRS
    angle_rad_to_rotate: float
    pivot_point: Point

    def __init__(self, territory: gpd.GeoDataFrame, rotation: bool | float | int = True):

        self.original_territory = self._gdf_to_poly(territory.copy())
        self.pivot_point = self.original_territory.centroid
        if rotation:
            self.rotation = True
            coord = self.original_territory.exterior.coords
            if isinstance(rotation, (float, int)):
                self.angle_rad_to_rotate = np.deg2rad(rotation)
                self.original_territory = Polygon(rotate_coords(coord, self.pivot_point, self.angle_rad_to_rotate))
            else:
                self.angle_rad_to_rotate = polygon_angle(self.original_territory)

                self.original_territory = Polygon(rotate_coords(coord, self.pivot_point, -self.angle_rad_to_rotate))
        else:
            self.rotation = False

    def _gdf_to_poly(self, gdf: gpd.GeoDataFrame) -> Polygon:
        self.local_crs = gdf.estimate_utm_crs()
        poly = gdf.to_crs(self.local_crs).union_all()
        if isinstance(poly, Polygon):
            return poly
        elif isinstance(poly, MultiPolygon):
            # TODO deal with multipolygon
            raise RuntimeError

    def _run(self, initial_func, *args, **kwargs):
        task_queue = multiprocessing.Queue()
        task_queue.put((initial_func, args, kwargs))
        res, roads = parallel_split_queue(task_queue, self.local_crs)
        if self.rotation:
            res.geometry = res.geometry.apply(
                lambda x: Polygon(rotate_coords(x.exterior.coords, self.pivot_point, self.angle_rad_to_rotate))
            )
            roads.geometry = roads.geometry.apply(
                lambda x: LineString(rotate_coords(x.coords, self.pivot_point, self.angle_rad_to_rotate))
            )
        return res, roads

    def zone2block(self, terr_zone: TerritoryZone) -> (gpd.GeoDataFrame, gpd.GeoDataFrame):
        return self._run(zone2block_initial, self.original_territory, terr_zone, local_crs=self.local_crs)

    def district2zone2block(self, funczone: FuncZone = basic_scenario) -> (gpd.GeoDataFrame, gpd.GeoDataFrame):
        return self._run(district2zone2block_initial, self.original_territory, funczone, local_crs=self.local_crs)

    def terr2district2zone2block(self, genplan: GenPlan = gen_plan) -> (gpd.GeoDataFrame, gpd.GeoDataFrame):
        return self._run(terr2district2zone2block_initial, self.original_territory, genplan, local_crs=self.local_crs)


def terr2district2zone2block_initial(task, **kwargs):
    territory, genplan = task
    areas_dict = genplan.func_zone_ratio
    local_crs = kwargs.get("local_crs")
    zones, roads = _split_polygon(
        polygon=territory,
        areas_dict=areas_dict,
        point_radius=poisson_n_radius.get(len(areas_dict), 0.1),
        local_crs=local_crs,
    )
    roads['road_lvl'] = 'high speed highway'
    tasks = []
    kwargs.update({"gen_plan": genplan.name})

    for _, zone in zones.iterrows():
        tasks.append((district2zone2block_initial, (zone.geometry, zone.zone_name), kwargs))
    return tasks, True, roads


def district2zone2block_initial(task, **kwargs):
    district, func_zone = task

    def recalculate_ratio(data, area):
        data["ratio"] = data["ratio"] / data["ratio"].sum()
        data["required_area"] = area * data["ratio"]
        data["good"] = data["min_block_area"] < data["required_area"]
        return data

    local_crs = kwargs.get("local_crs")
    area = district.area
    terr_zones = pd.DataFrame.from_dict(
        {terr_zone: [ratio, terr_zone.min_block_area] for terr_zone, ratio in func_zone.zones_ratio.items()},
        orient="index",
        columns=["ratio", "min_block_area"],
    )

    terr_zones = recalculate_ratio(terr_zones, area)
    while not terr_zones["good"].all():
        terr_zones = terr_zones[terr_zones["good"]].copy()
        terr_zones = recalculate_ratio(terr_zones, area)

    zones, roads = _split_polygon(
        polygon=district,
        areas_dict=terr_zones["ratio"].to_dict(),
        point_radius=poisson_n_radius.get(len(terr_zones), 0.1),
        local_crs=local_crs,
    )
    roads['road_lvl'] = 'regulated highway'
    tasks = []
    kwargs.update({"func_zone": func_zone.name})

    # data = {key: [value] * len(zones) for key, value in kwargs.items() if key != "local_crs"}
    # zones = gpd.GeoDataFrame(data=data, geometry=zones.geometry, crs=kwargs.get("local_crs"))

    for _, zone in zones.iterrows():
        tasks.append((zone2block_initial, (zone.geometry, zone.zone_name), kwargs))

    return tasks, True, roads


def zone2block_initial(task, **kwargs):
    zone_to_split, terr_zone = task
    kwargs.update({"terr_zone": terr_zone.name})
    target_area = zone_to_split.area
    min_area = terr_zone.min_block_area
    max_delimeter = 6
    temp_area = min_area
    delimeters = []
    while temp_area < target_area:
        temp_area = temp_area * max_delimeter
        delimeters.append(max_delimeter)
    if len(delimeters) == 0:
        return [(zone2block_splitter, (zone_to_split, [1], min_area, 1), kwargs)], True, gpd.GeoDataFrame()

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

    return [(zone2block_splitter, (zone_to_split, delimeters, min_area, 1), kwargs)], True, gpd.GeoDataFrame()


def zone2block_splitter(task, **kwargs):
    polygon, delimeters, min_area, deep = task

    if deep == len(delimeters):
        n_areas = min(8, int(polygon.area // min_area))
        if n_areas in [0, 1]:
            data = {key: [value] for key, value in kwargs.items() if key != "local_crs"}
            blocks = gpd.GeoDataFrame(data=data, geometry=[polygon], crs=kwargs.get("local_crs"))
            return blocks, False, gpd.GeoDataFrame()
    else:
        n_areas = delimeters[deep - 1]
    areas_dict = {x: 1 / n_areas for x in range(n_areas)}
    blocks, roads = _split_polygon(
        polygon=polygon,
        areas_dict=areas_dict,
        point_radius=poisson_n_radius.get(n_areas, 0.1),
        local_crs=kwargs.get("local_crs"),
    )
    roads['road_lvl'] = f'local roads, level {round(deep / 10, 1)}'
    if deep == len(delimeters):
        data = {key: [value] * len(blocks) for key, value in kwargs.items() if key != "local_crs"}
        blocks = gpd.GeoDataFrame(data=data, geometry=blocks.geometry, crs=kwargs.get("local_crs"))
        return blocks, False, roads
    else:
        deep = deep + 1
        blocks = blocks.geometry
        try:
            to_return = [(zone2block_splitter, (Polygon(poly), delimeters, min_area, deep), kwargs) for poly in blocks if
                         poly is not None]
        except Exception:
            raise RuntimeError([poly for poly in blocks])
        return to_return, True, roads


def parallel_split_queue(task_queue: multiprocessing.Queue, local_crs) -> (gpd.GeoDataFrame, gpd.GeoDataFrame):
    splitted = []
    roads_all = []
    with concurrent.futures.ProcessPoolExecutor() as executor:
        future_to_task = {}
        while True:
            while not task_queue.empty() and len(future_to_task) < executor._max_workers:
                try:
                    func, task, kwargs = task_queue.get_nowait()

                    future = executor.submit(func, task, **kwargs)
                    future_to_task[future] = task
                except multiprocessing.queues.Empty:
                    break

            done, _ = concurrent.futures.wait(
                future_to_task.keys(), timeout=0, return_when=concurrent.futures.FIRST_COMPLETED
            )
            for future in done:
                future_to_task.pop(future)

                result, create_tasks, roads = future.result()
                if create_tasks:
                    for func, new_task, kwargs in result:
                        task_queue.put((func, new_task, kwargs))
                else:
                    splitted.append(result)
                roads_all.append(roads)

            if not future_to_task and task_queue.empty():
                break
    return (gpd.GeoDataFrame(pd.concat(splitted, ignore_index=True), crs=local_crs, geometry="geometry"),
            gpd.GeoDataFrame(pd.concat(roads_all, ignore_index=True), crs=local_crs, geometry="geometry"))


def _split_polygon(
        polygon: Polygon,
        areas_dict: dict,
        local_crs: CRS,
        point_radius: float = 0.1,
        zone_connections: list = None,
) -> (gpd.GeoDataFrame, gpd.GeoDataFrame):
    if zone_connections is None:
        zone_connections = []

    def create_polygons(site2idx, site2room, idx2vtxv, vtxv2xy):
        poly_coords = []
        poly_sites = []
        for i_site in range(len(site2idx) - 1):
            if site2room[i_site] == np.iinfo(np.uint32).max:
                continue

            num_vtx_in_site = site2idx[i_site + 1] - site2idx[i_site]
            if num_vtx_in_site == 0:
                continue

            vtx2xy = []
            for i_vtx in range(num_vtx_in_site):  # collecting poly
                i_vtxv = idx2vtxv[site2idx[i_site] + i_vtx]  # founding vertex id
                vtx2xy.append((vtxv2xy[i_vtxv * 2], vtxv2xy[i_vtxv * 2 + 1]))  # adding vertex xy to poly
            poly_sites.append(site2room[i_site])
            poly_coords.append(Polygon(vtx2xy))

        return poly_coords, poly_sites

    bounds = polygon.bounds
    normalized_polygon = Polygon(normalize_coords(polygon.exterior.coords, bounds))
    attempts = 10
    for i in range(attempts):  # 10 attempts
        try:
            poisson_points = generate_points(normalized_polygon, point_radius)
            full_area = normalized_polygon.area
            areas = pd.DataFrame(list(areas_dict.items()), columns=["zone_name", "ratio"])

            areas["ratio"] = areas["ratio"] / areas["ratio"].sum()
            areas["area"] = areas["ratio"] * full_area

            areas["ratio_sqrt"] = np.sqrt(areas["ratio"]) / np.sqrt(areas["ratio"]).sum()
            areas['area_sqrt'] = areas["ratio_sqrt"] * full_area

            areas.sort_values(by="ratio", ascending=True, inplace=True)
            area_per_site = areas['area_sqrt'].sum() / (len(poisson_points))
            areas["site_indeed"] = np.floor(areas["area_sqrt"] / area_per_site).astype(int)

            total_points_assigned = areas["site_indeed"].sum()
            points_difference = len(poisson_points) - total_points_assigned

            if points_difference > 0:  #
                for _ in range(points_difference):
                    areas.loc[areas["site_indeed"].idxmin(), "site_indeed"] += 1
            elif points_difference < 0:
                for _ in range(abs(points_difference)):
                    areas.loc[areas["site_indeed"].idxmax(), "site_indeed"] -= 1
            site2room = np.random.permutation(np.repeat(areas.index, areas["site_indeed"]))

            normalized_border = [
                round(item, 8)
                for sublist in normalized_polygon.exterior.segmentize(0.1).normalize().coords[::-1]
                for item in sublist
            ]

            res = optimize_space(
                vtxl2xy=normalized_border,
                site2xy=poisson_points.flatten().round(8).tolist(),
                site2room=site2room.tolist(),
                site2xy2flag=[0.0 for _ in range(len(site2room) * 2)],
                room2area_trg=areas["area"].sort_index().round(8).tolist(),
                room_connections=zone_connections,
                create_gif=False,
            )
            site2idx = res[0]  # number of points [0,5,10,15,20] means there are 4 polygons with indexes 0..5 etc
            idx2vtxv = res[1]  # node indexes for each voronoi poly
            vtxv2xy = res[2]  # all points from generation (+bounds)
            site2room = site2room.tolist()
            edge2vtxv_wall = res[3]  # complete walls/roads

            vtxv2xy = denormalize_coords([coords for coords in np.array(vtxv2xy).reshape(int(len(vtxv2xy) / 2), 2)],
                                         bounds)

            polygons, poly_sites = create_polygons(site2idx, site2room, idx2vtxv, np.array(vtxv2xy).flatten().tolist())
            devided_zones = (
                gpd.GeoDataFrame(geometry=polygons, data=poly_sites, columns=["zone_id"], crs=local_crs)
                .dissolve("zone_id")
                .reset_index()
            )
            if len(devided_zones) != len(areas):
                raise ValueError(f"Number of devided_zones does not match {len(areas)}: {len(devided_zones)}")

            devided_zones = devided_zones.merge(areas.reset_index(), left_on="zone_id", right_on="index").drop(
                columns=["index", "area", "site_indeed", "zone_id"]
            )

            # devided_zones.geometry = devided_zones.geometry.apply(
            #     lambda geom: max(geom.geoms, key=lambda x: x.area) if isinstance(geom, MultiPolygon) else geom
            # )
            devided_zones = devided_zones.explode(ignore_index=True)
            new_area = devided_zones.area.sum()
            if new_area > polygon.area * 1.1 or new_area < polygon.area * 0.9:
                raise ValueError(f"Area of devided_zones does not match {new_area}:{polygon.area}")

            new_roads = [
                (vtxv2xy[x[0]], vtxv2xy[x[1]]) for x in
                np.array(edge2vtxv_wall).reshape(int(len(edge2vtxv_wall) / 2), 2)
            ]
            new_roads = gpd.GeoDataFrame(geometry=[LineString(x) for x in new_roads], crs=local_crs)
            return devided_zones, new_roads

        except UnboundLocalError as e:
            raise ValueError(areas)
        except Exception as e:
            if i + 1 == attempts:
                raise ValueError(
                    f' areas:{areas} \n'
                    f' len_points: {len(poisson_points)} \n'
                    f' poly: {normalized_polygon}, \n'
                    f' radius: {point_radius}, \n'
                    f' {e}')
            # return gpd.GeoDataFrame()
