import concurrent.futures
import multiprocessing

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import CRS
from rust_optimizer import optimize_space
from shapely.geometry import Point, Polygon, MultiPolygon, LineString

from gen_planner.python.src.func_zones import FuncZone, Scenario, basic_scenario, gen_plan, GenPlan
from gen_planner.python.src.geom_utils import (
    rotate_coords,
    polygon_angle,
    normalize_coords,
    denormalize_coords,
    generate_points,
)

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

    def zone2block(self, func_zone: FuncZone) -> gpd.GeoDataFrame:
        zone_to_split = self.original_territory
        task_queue = multiprocessing.Queue()
        task_queue.put((zone2block_initial, (zone_to_split, func_zone), {'local_crs': self.local_crs}))
        res = parallel_split_queue(task_queue, self.local_crs)
        res.geometry = res.geometry.apply(
            lambda x: Polygon(rotate_coords(x.exterior.coords, self.pivot_point, self.angle_rad_to_rotate)))
        return res

    def district2zone2block(self, scenario: Scenario = basic_scenario) -> gpd.GeoDataFrame:
        district = self.original_territory
        task_queue = multiprocessing.Queue()
        task_queue.put((district2zone2block_initial, (district, scenario), {'local_crs': self.local_crs}))
        res = parallel_split_queue(task_queue, self.local_crs)
        # res = district2zone2block_initial((district,scenario),local_crs=self.local_crs)
        res.geometry = res.geometry.apply(
            lambda x: Polygon(rotate_coords(x.exterior.coords, self.pivot_point, self.angle_rad_to_rotate)))
        return res

    def terr2district2zone2block(self, polygon: Polygon, district_areas: list, genplan: GenPlan = gen_plan):
        pass

    def run(self):
        # first iteration

        pass


def district2zone2block_initial(task, **kwargs):
    district, scenario = task

    def recalculate_ratio(data, area):
        data['ratio'] = data['ratio'] / data['ratio'].sum()
        data['required_area'] = area * data['ratio']
        data['good'] = data['min_block_area'] < data['required_area']
        return data

    local_crs = kwargs.get('local_crs')
    area = district.area
    func_zones = pd.DataFrame.from_dict(
        {func_zone: [ratio, func_zone.min_block_area] for func_zone, ratio in scenario.zones_ratio.items()},
        orient='index', columns=['ratio', 'min_block_area'])

    func_zones = recalculate_ratio(func_zones, area)
    while not func_zones['good'].all():
        func_zones = func_zones[func_zones['good']].copy()
        func_zones = recalculate_ratio(func_zones, area)

    zones = _split_polygon(polygon=district, areas_dict=func_zones['ratio'].to_dict(),
                           point_radius=poisson_n_radius.get(len(func_zones), 0.1),
                           local_crs=local_crs)
    tasks = []
    kwargs.update({'scenario': scenario.name})
    for _, zone in zones.iterrows():
        tasks.append((zone2block_initial, (zone.geometry, zone.zone_name), kwargs))
    return tasks, True


def zone2block_initial(task, **kwargs):
    zone_to_split, func_zone = task
    kwargs.update({'func_zone': func_zone.name})
    target_area = zone_to_split.area
    min_area = func_zone.min_block_area
    max_delimeter = 6
    temp_area = min_area
    delimeters = []
    while temp_area < target_area:
        temp_area = temp_area * max_delimeter
        delimeters.append(max_delimeter)
    if len(delimeters) ==0:
        return [(zone2block_splitter, (zone_to_split, [1], min_area, 1), kwargs)], True

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

    return [(zone2block_splitter, (zone_to_split, delimeters, min_area, 1), kwargs)], True


def zone2block_splitter(task, **kwargs):
    polygon, delimeters, min_area, deep = task

    if deep == len(delimeters):
        n_areas = min(8, int(polygon.area // min_area))
        if n_areas in [0, 1]:
            data = {key: [value] for key, value in kwargs.items() if key != 'local_crs'}
            res = gpd.GeoDataFrame(data=data, geometry=[polygon], crs=kwargs.get('local_crs', None))
            return res, False
    else:
        n_areas = delimeters[deep - 1]
    areas_dict = {x: 1 / n_areas for x in range(n_areas)}
    res = _split_polygon(polygon=polygon, areas_dict=areas_dict, point_radius=poisson_n_radius.get(n_areas, 0.1),
                         local_crs=kwargs.get('local_crs'))
    if deep == len(delimeters):
        data = {key: [value] * len(res) for key, value in kwargs.items() if key != 'local_crs'}
        res = gpd.GeoDataFrame(data=data, geometry=res.geometry, crs=kwargs.get('local_crs', None))
        return res, False
    else:
        deep = deep + 1
        res = res.geometry
        return [(zone2block_splitter, (poly, delimeters, min_area, deep), kwargs) for poly in res if
                poly is not None], True


def parallel_split_queue(task_queue: multiprocessing.Queue, local_crs) -> gpd.GeoDataFrame:
    splitted = []

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

            done, _ = concurrent.futures.wait(future_to_task.keys(), timeout=0,
                                              return_when=concurrent.futures.FIRST_COMPLETED)
            for future in done:
                future_to_task.pop(future)

                result, create_tasks = future.result()
                if create_tasks:
                    for func, new_task, kwargs in result:
                        task_queue.put((func, new_task, kwargs))
                else:
                    splitted.append(result)

            if not future_to_task and task_queue.empty():
                break
    return gpd.GeoDataFrame(pd.concat(splitted, ignore_index=True), crs=local_crs, geometry='geometry')


def _split_polygon(
        polygon: Polygon, areas_dict: dict, local_crs: CRS, point_radius: float = 0.1, zone_connections: list = None,
) -> gpd.GeoDataFrame:
    if zone_connections is None:
        zone_connections = []

    bounds = polygon.bounds
    normalized_polygon = Polygon(normalize_coords(polygon.exterior.coords, bounds))
    for i in range(5):  # 10 attempts
        try:
            poisson_points = generate_points(normalized_polygon, point_radius)
            full_area = normalized_polygon.area
            areas = pd.DataFrame(list(areas_dict.items()), columns=["zone_name", "ratio"])
            areas["ratio"] = areas["ratio"] / areas["ratio"].sum()
            areas["area"] = areas["ratio"] * full_area
            areas.sort_values(by="ratio", ascending=True, inplace=True)
            area_per_site = full_area / (len(poisson_points))
            areas["site_indeed"] = round(areas["area"] / area_per_site).astype(int)
            site2room = np.random.permutation(np.repeat(areas.index, areas["site_indeed"]))
            poisson_points = poisson_points[: len(site2room)]
            site2room = site2room[: len(poisson_points)].astype(int)
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
            break
        except RuntimeError:
            if i + 1 == 10:
                return gpd.GeoDataFrame()

    site2idx = res[0]  # number of points [0,5,10,15,20] means there are 4 polygons with indexes 0..5 etc
    idx2vtxv = res[1]  # node indexes for each voronoi poly
    vtxv2xy = res[2]  # all points from generation (+bounds)
    site2room = site2room.tolist()
    edge2vtxv_wall = res[3]  # complete walls/roads

    vtxv2xy = denormalize_coords([coords for coords in np.array(vtxv2xy).reshape(int(len(vtxv2xy) / 2), 2)], bounds)

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

        return poly_coords,poly_sites

    polygons,poly_sites = create_polygons(site2idx, site2room, idx2vtxv, np.array(vtxv2xy).flatten().tolist())

    devided_zones = gpd.GeoDataFrame(geometry=polygons, data=poly_sites, columns=['zone_id'], crs=local_crs).dissolve(
        'zone_id').reset_index()
    devided_zones = devided_zones.merge(areas.reset_index(), left_on="zone_id", right_on="index").drop(
        columns=["index", "area", "site_indeed", "zone_id"]
    )
    devided_zones.geometry = devided_zones.geometry.apply(
        lambda geom: max(geom.geoms, key=lambda x: x.area) if isinstance(geom, MultiPolygon) else geom)
    new_roads = [
        (vtxv2xy[x[0]], vtxv2xy[x[1]])
        for x in np.array(edge2vtxv_wall).reshape(int(len(edge2vtxv_wall) / 2), 2)
    ]
    new_roads = [LineString(x) for x in new_roads]

    return devided_zones
