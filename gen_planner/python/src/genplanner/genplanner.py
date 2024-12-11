import concurrent.futures
import multiprocessing
import time

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import CRS
from shapely.geometry import Point, Polygon, MultiPolygon, LineString
from shapely.ops import polygonize

from gen_planner.python.src.zoning import TerritoryZone, FuncZone, basic_func_zone, gen_plan, GenPlan
from gen_planner.python.src.tasks import (
    zone2block_initial,
    terr2district2zone2block_initial,
    district2zone2block_initial,
)
from gen_planner.python.src.utils.geom_utils import (
    rotate_coords,
    polygon_angle,
    polygons_to_linestring,
)


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
        roads_poly = roads.copy()
        roads_poly.geometry = roads_poly.apply(lambda x: x.geometry.buffer(x.roads_width / 2, resolution=4), axis=1)
        roads_poly = roads_poly.union_all()
        all_data = pd.concat([res, gpd.GeoDataFrame(geometry=[roads_poly], crs=self.local_crs)])["geometry"]
        polygons = gpd.GeoDataFrame(
            geometry=list(polygonize(all_data.apply(polygons_to_linestring).union_all())), crs=self.local_crs
        )
        res.geometry = res.geometry.buffer(-10).representative_point()
        res = res.sjoin(polygons, how="left", predicate="within")
        res["geometry"] = res["index_right"].map(polygons["geometry"])
        res.drop(columns=["index_right"], inplace=True)
        return res, roads

    def zone2block(self, terr_zone: TerritoryZone) -> (gpd.GeoDataFrame, gpd.GeoDataFrame):
        return self._run(zone2block_initial, self.original_territory, terr_zone, local_crs=self.local_crs)

    def district2zone2block(self, funczone: FuncZone = basic_func_zone) -> (gpd.GeoDataFrame, gpd.GeoDataFrame):
        return self._run(district2zone2block_initial, self.original_territory, funczone, local_crs=self.local_crs)

    def terr2district2zone2block(self, genplan: GenPlan = gen_plan) -> (gpd.GeoDataFrame, gpd.GeoDataFrame):
        return self._run(terr2district2zone2block_initial, self.original_territory, genplan, local_crs=self.local_crs)


def parallel_split_queue(task_queue: multiprocessing.Queue, local_crs) -> (gpd.GeoDataFrame, gpd.GeoDataFrame):
    splitted = []
    roads_all = []
    with concurrent.futures.ProcessPoolExecutor() as executor:
        future_to_task = {}
        while True:
            while not task_queue.empty() and len(future_to_task) < executor._max_workers:
                func, task, kwargs = task_queue.get_nowait()
                future = executor.submit(func, task, **kwargs)

                future_to_task[future] = task

            done, _ = concurrent.futures.wait(future_to_task.keys(), return_when=concurrent.futures.FIRST_COMPLETED)

            for future in done:
                future_to_task.pop(future)
                result, create_tasks, roads = future.result()
                if create_tasks:
                    for func, new_task, kwargs in result:
                        task_queue.put((func, new_task, kwargs))
                else:
                    splitted.append(result)
                roads_all.append(roads)
            time.sleep(0.01)
            if not future_to_task and task_queue.empty():
                break
    return (
        gpd.GeoDataFrame(pd.concat(splitted, ignore_index=True), crs=local_crs, geometry="geometry"),
        gpd.GeoDataFrame(pd.concat(roads_all, ignore_index=True), crs=local_crs, geometry="geometry"),
    )
