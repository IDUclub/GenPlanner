import concurrent.futures
import multiprocessing
import time

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import CRS
from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.ops import polygonize

from app.gen_planner.python.src.tasks import (
    poly2block_initial,
    poly2func2terr2block_initial,
    poly2terr2block_initial,
    polygon_splitter,
    multipoly2terr2block_initial,
)
from app.gen_planner.python.src.utils import polygon_angle, geometry_to_multilinestring, rotate_coords, rotate_poly
from app.gen_planner.python.src.zoning import FuncZone, GenPlan, TerritoryZone, basic_func_zone, gen_plan


class GenPlanner:
    original_territory: gpd.GeoDataFrame
    transformed_poly: Polygon | MultiPolygon
    local_crs: CRS
    angle_rad_to_rotate: float
    pivot_point: Point
    source_multipolygon: bool = False

    def __init__(self, territory: gpd.GeoDataFrame, rotation: bool | float | int = True):
        self.transformed_poly = self._gdf_to_poly(territory.copy())
        self.pivot_point = self.transformed_poly.centroid
        if rotation:
            self.rotation = True

            if rotation is not True:
                self.angle_rad_to_rotate = np.deg2rad(rotation)
                self.transformed_poly = rotate_poly(self.transformed_poly, self.pivot_point, -self.angle_rad_to_rotate)
            else:
                self.angle_rad_to_rotate = polygon_angle(self.transformed_poly)
                self.transformed_poly = rotate_poly(self.transformed_poly, self.pivot_point, -self.angle_rad_to_rotate)
        else:
            self.rotation = False

    def _gdf_to_poly(self, gdf: gpd.GeoDataFrame) -> Polygon | MultiPolygon:
        self.original_territory = gdf.copy()
        self.local_crs = gdf.estimate_utm_crs()
        if len(gdf) == 1:
            poly = gdf.to_crs(self.local_crs).union_all()
        else:
            self.source_multipolygon = True
            gdf = gdf[gdf.geom_type.isin(["MultiPolygon", "Polygon"])]
            poly = MultiPolygon(gdf.to_crs(self.local_crs).geometry.explode().to_list())
        return poly

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
            geometry=list(polygonize(all_data.apply(geometry_to_multilinestring).union_all())), crs=self.local_crs
        )
        polygons_points = polygons.copy()
        polygons_points.geometry = polygons_points.representative_point()
        to_kick = polygons_points.sjoin(
            gpd.GeoDataFrame(geometry=[roads_poly], crs=self.local_crs), predicate="within"
        ).index
        polygons_points.drop(to_kick, inplace=True)
        polygons_points = polygons_points.sjoin(res, how="inner", predicate="within")
        polygons_points.geometry = polygons.loc[polygons_points.index].geometry
        res = polygons_points
        res.drop(columns=["index_right"], inplace=True)
        return res, roads

    def split_poly(self, zones_ratio_dict: dict = None, zones_n: int = None, roads_width=None):
        if zones_ratio_dict is None and zones_n is None:
            raise RuntimeError("Either zones_ratio_dict or zones_n must be set")
        if len(zones_ratio_dict) in [0, 1]:
            raise ValueError("zones_ratio_dict ")
        if zones_n is not None:
            zones_ratio_dict = {x: 1 / zones_n for x in range(zones_n)}
        if len(zones_ratio_dict) > 8:
            raise RuntimeError("Use poly2block, to split more than 8 parts")
        return self._run(
            polygon_splitter, self.transformed_poly, zones_ratio_dict, roads_width, local_crs=self.local_crs
        )

    def poly2block(self, terr_zone: TerritoryZone) -> (gpd.GeoDataFrame, gpd.GeoDataFrame):
        if self.source_multipolygon:
            raise NotImplementedError("Multipolygon source is not supported yet")
        return self._run(poly2block_initial, self.transformed_poly, terr_zone, local_crs=self.local_crs)

    def poly2terr(self, funczone: FuncZone = basic_func_zone) -> (gpd.GeoDataFrame, gpd.GeoDataFrame):
        if self.source_multipolygon:
            return self._run(
                multipoly2terr2block_initial, self.transformed_poly, funczone, False, local_crs=self.local_crs
            )
        return self._run(poly2terr2block_initial, self.transformed_poly, funczone, False, local_crs=self.local_crs)

    def poly2terr2block(self, funczone: FuncZone = basic_func_zone) -> (gpd.GeoDataFrame, gpd.GeoDataFrame):
        if self.source_multipolygon:
            return self._run(
                multipoly2terr2block_initial, self.transformed_poly, funczone, True, local_crs=self.local_crs
            )
        return self._run(poly2terr2block_initial, self.transformed_poly, funczone, True, local_crs=self.local_crs)

    def poly2func(self, genplan: GenPlan = gen_plan) -> (gpd.GeoDataFrame, gpd.GeoDataFrame):
        if self.source_multipolygon:
            raise NotImplementedError("Multipolygon source is not supported yet")
        return self._run(poly2func2terr2block_initial, self.transformed_poly, genplan, False, local_crs=self.local_crs)

    def poly2func2terr2block(self, genplan: GenPlan = gen_plan) -> (gpd.GeoDataFrame, gpd.GeoDataFrame):
        if self.source_multipolygon:
            raise NotImplementedError("Multipolygon source is not supported yet")
        return self._run(poly2func2terr2block_initial, self.transformed_poly, genplan, True, local_crs=self.local_crs)


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
