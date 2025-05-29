import concurrent.futures
import multiprocessing
import time
from typing import Literal

import geopandas as gpd
import numpy as np
import pandas as pd
from loguru import logger
from pyproj import CRS, Transformer
from shapely import Point
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import polygonize

from app.gen_planner.python.src.tasks import (
    feature2terr_zones_initial,
    multi_feature2terr_zones_initial,
    multi_feature2blocks_initial,
    gdf_splitter,
    poly2func2terr2block_initial,
)
from app.gen_planner.python.src.utils import geometry_to_multilinestring
from app.gen_planner.python.src.zoning import FuncZone, GenPlan, TerritoryZone, basic_func_zone, gen_plan


class GenPlanner:
    original_territory: gpd.GeoDataFrame
    original_cr: CRS

    territory_to_work_with: gpd.GeoDataFrame
    local_crs: CRS
    angle_rad_to_rotate: float | Literal["auto"]
    source_multipolygon: bool = False

    # geometry_transformer4326: Transformer
    dev_mod: bool = False

    def __init__(
            self,
            features: gpd.GeoDataFrame,
            rotation: bool = True,
            rotation_angle: float | Literal["auto"] = "auto",
            **kwargs,
    ):
        features.reset_index(names="new_node_index")
        self._create_working_gdf(features.copy())
        if rotation:
            self.rotation = True
            if rotation_angle != "auto":
                self.angle_rad_to_rotate = np.deg2rad(rotation)
            else:
                self.angle_rad_to_rotate = rotation_angle
        else:
            self.rotation = False
        if "dev_mod" in kwargs:
            self.dev_mod = True
            logger.info("Dev mod activated, no more ProcessPool")

    def _create_working_gdf(self, gdf: gpd.GeoDataFrame) -> Polygon | MultiPolygon:
        self.original_territory = gdf.copy()
        self.original_crs = gdf.crs
        self.local_crs = gdf.estimate_utm_crs()
        gdf = gdf.to_crs(self.local_crs).explode(index_parts=False)
        gdf = gdf[gdf.geom_type.isin(["MultiPolygon", "Polygon"])]
        if len(gdf) == 0:
            raise TypeError("No valid geometries in provided GeoDataFrame")
        elif len(gdf) == 1:
            self.source_multipolygon = False
        else:
            self.source_multipolygon = True
        self.territory_to_work_with = gdf.to_crs(self.local_crs)

    def _run(self, initial_func, *args, **kwargs):
        task_queue = multiprocessing.Queue()
        kwargs.update({"dev_mod": self.dev_mod})
        task_queue.put((initial_func, args, kwargs))
        res, roads = parallel_split_queue(task_queue, self.local_crs, dev=self.dev_mod)

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

    def _check_fixed_zones(self, zones_ratio_dict, fixed_zones: gpd.GeoDataFrame) -> gpd.GeoDataFrame:

        if not (fixed_zones.geom_type == "Point").all():
            raise TypeError('fixed_zones must be a MultiPolygon')

        return fixed_zones


def split_features(
        self, zones_ratio_dict: dict = None, zones_n: int = None, roads_width=None,
        fixed_zones: gpd.GeoDataFrame = None
):
    """
    Splits every feature in working gdf according to provided zones_ratio_dict or zones_n

    :param fixed_zones:
    :param zones_ratio_dict:
    :param zones_n:
    :param roads_width:
    :return:
    """
    if zones_ratio_dict is None and zones_n is None:
        raise RuntimeError("Either zones_ratio_dict or zones_n must be set")
    if zones_ratio_dict is not None and len(zones_ratio_dict) in [0, 1]:
        raise ValueError("zones_ratio_dict ")
    if fixed_zones is None:
        fixed_zones = gpd.GeoDataFrame()
    if len(fixed_zones) > 0:
        if zones_ratio_dict is None:
            raise ValueError("zones_ratio_dict should not be None for generating fixed zones")
        fixed_zones = fixed_zones.to_crs(self.local_crs)
    if zones_n is not None:
        zones_ratio_dict = {x: 1 / zones_n for x in range(zones_n)}
    if len(zones_ratio_dict) > 8:
        raise RuntimeError("Use poly2block, to split more than 8 parts")
    args = (self.territory_to_work_with, zones_ratio_dict, roads_width, fixed_zones)
    return self._run(gdf_splitter, *args)


def features2blocks(self, terr_zone: TerritoryZone) -> (gpd.GeoDataFrame, gpd.GeoDataFrame):
    if not isinstance(terr_zone, TerritoryZone):
        raise TypeError("terr_zone arg must be of type TerritoryZone")
    if not "territory_zone" in self.territory_to_work_with.columns:
        logger.warning(
            f"territory_zone column not found in working gdf. All geometry's territory zone set to {terr_zone}"
        )
        self.territory_to_work_with["territory_zone"] = terr_zone
    return self._run(multi_feature2blocks_initial, self.territory_to_work_with)


def features2terr_zones(self, funczone: FuncZone = basic_func_zone, fixed_terr_zones: gpd.GeoDataFrame = None) -> (
        gpd.GeoDataFrame, gpd.GeoDataFrame):
    self._features2terr_zones(funczone, split_further=False)


def features2terr_zones2blocks(self, funczone: FuncZone = basic_func_zone,
                               fixed_terr_zones: gpd.GeoDataFrame = None) -> (gpd.GeoDataFrame, gpd.GeoDataFrame):
    self._features2terr_zones(funczone, split_further=True)


def _features2terr_zones(self, funczone: FuncZone = basic_func_zone, split_further=False) -> (gpd.GeoDataFrame,
                                                                                              gpd.GeoDataFrame):
    args = self.territory_to_work_with, funczone, split_further
    if self.source_multipolygon:
        return self._run(multi_feature2terr_zones_initial, *args)
    return self._run(feature2terr_zones_initial, *args)


# def poly2func(self, genplan: GenPlan = gen_plan) -> (gpd.GeoDataFrame, gpd.GeoDataFrame):
#     if self.source_multipolygon:
#         raise NotImplementedError("Multipolygon source is not supported yet")
#     return self._run(
#         poly2func2terr2block_initial, self.territory_to_work_with, genplan, False, local_crs=self.local_crs
#     )
#
# def poly2func2terr2block(self, genplan: GenPlan = gen_plan) -> (gpd.GeoDataFrame, gpd.GeoDataFrame):
#     if self.source_multipolygon:
#         raise NotImplementedError("Multipolygon source is not supported yet")
#     return self._run(
#         poly2func2terr2block_initial, self.territory_to_work_with, genplan, True, local_crs=self.local_crs
#     )


def parallel_split_queue(
        task_queue: multiprocessing.Queue, local_crs, dev=False
) -> (gpd.GeoDataFrame, gpd.GeoDataFrame):
    splitted = []
    roads_all = []
    if dev:
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    else:
        executor = concurrent.futures.ProcessPoolExecutor()
    with executor:
        future_to_task = {}
        while True:
            while not task_queue.empty() and len(future_to_task) < executor._max_workers:
                func, task, kwargs = task_queue.get_nowait()
                future = executor.submit(func, task, **kwargs)

                future_to_task[future] = task

            done, _ = concurrent.futures.wait(future_to_task.keys(), return_when=concurrent.futures.FIRST_COMPLETED)

            for future in done:
                future_to_task.pop(future)
                result: dict = future.result()
                new_tasks = result.get("new_tasks", [])
                if len(new_tasks) > 0:
                    for func, new_task, kwargs in new_tasks:
                        task_queue.put((func, new_task, kwargs))

                generated_zones = result.get("generation", gpd.GeoDataFrame())
                if len(generated_zones) > 0:
                    splitted.append(generated_zones)

                generated_roads = result.get("generated_roads", gpd.GeoDataFrame())
                if len(generated_roads) > 0:
                    roads_all.append(generated_roads)

            time.sleep(0.01)
            if not future_to_task and task_queue.empty():
                break

    if len(roads_all) > 0:
        roads_to_return = gpd.GeoDataFrame(pd.concat(roads_all, ignore_index=True), crs=local_crs, geometry="geometry")
    else:
        roads_to_return = gpd.GeoDataFrame()

    return (
        gpd.GeoDataFrame(pd.concat(splitted, ignore_index=True), crs=local_crs, geometry="geometry"),
        roads_to_return,
    )
