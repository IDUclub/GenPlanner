import concurrent.futures
import multiprocessing
import time

import geopandas as gpd
import pandas as pd
from loguru import logger
from pyproj import CRS
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import polygonize, unary_union

from app.gen_planner.python.src._config import config
from app.gen_planner.python.src.tasks import (
    feature2terr_zones_initial,
    gdf_splitter,
    multi_feature2blocks_initial,
    multi_feature2terr_zones_initial,
)
from app.gen_planner.python.src.utils import (
    explode_linestring,
    extend_linestring,
    geometry_to_multilinestring,
    patch_polygon_interior,
    territory_splitter,
)
from app.gen_planner.python.src.zoning import FuncZone, TerritoryZone, basic_func_zone

roads_width_def = config.roads_width_def.copy()


class GenPlanner:
    original_territory: gpd.GeoDataFrame
    original_crs: CRS

    territory_to_work_with: gpd.GeoDataFrame
    local_crs: CRS
    user_valid_roads: gpd.GeoDataFrame
    source_multipolygon: bool = False

    dev_mod: bool = False

    def __init__(
        self,
        features: gpd.GeoDataFrame,
        roads: gpd.GeoDataFrame = None,
        exclude_features: gpd.GeoDataFrame = None,
        simplify_geometry: bool = True,
        **kwargs,
    ):
        self.original_territory = features.copy()
        self.original_crs = features.crs
        self.local_crs = features.estimate_utm_crs()

        if roads is None:
            roads = gpd.GeoDataFrame()
        if exclude_features is None:
            exclude_features = gpd.GeoDataFrame()
        self._create_working_gdf(
            self.original_territory.copy(),
            roads.copy(),
            exclude_features.copy(),
            simplify_geometry,
            kwargs.get("simplify_value", 10),
        )
        if "dev_mod" in kwargs:
            self.dev_mod = True
            logger.info("Dev mod activated, no more ProcessPool")

    def _create_working_gdf(
        self,
        gdf: gpd.GeoDataFrame,
        roads: gpd.GeoDataFrame,
        exclude_features: gpd.GeoDataFrame,
        simplify_geometry: bool,
        simplify_value: float,
    ) -> Polygon | MultiPolygon:

        gdf = gdf[gdf.geom_type.isin(["MultiPolygon", "Polygon"])]

        if len(gdf) == 0:
            raise TypeError("No valid geometries in provided GeoDataFrame")

        gdf = gdf.to_crs(self.local_crs)

        # gdf = territory_splitter(gdf, exclude_features, return_splitters=False)
        if len(exclude_features) > 0:
            exclude_features = exclude_features.to_crs(self.local_crs)
            exclude_features = exclude_features.clip(self.original_territory.to_crs(self.local_crs))
            # exclude_features.geometry = exclude_features.geometry.buffer(0.1, resolution=1)
            gdf = territory_splitter(gdf, exclude_features, return_splitters=False).reset_index(drop=True)
            # exclude_union = exclude_features.union_all()
            # gdf.geometry = gdf.geometry.apply(lambda geom: geom.difference(exclude_union))
            # gdf = gdf.explode(ignore_index=True)

        if simplify_geometry:
            gdf.geometry = gdf.geometry.simplify(simplify_value)

        if len(roads) > 0:
            roads = roads.to_crs(self.local_crs)
            # if simplify_geometry:
            #     print('simplified on', simplify_value)
            #     roads.geometry = roads.geometry.simplify(simplify_value)
            roads = roads.explode(ignore_index=True)
            splitters_roads = roads.copy()
            splitters_roads.geometry = splitters_roads.geometry.normalize()
            splitters_roads = splitters_roads[~splitters_roads.geometry.duplicated(keep="first")]
            splitters_roads.geometry = splitters_roads.geometry.apply(extend_linestring, distance=5)

            gdf = territory_splitter(gdf, splitters_roads, return_splitters=False).reset_index(drop=True)
            splitters_lines = gpd.GeoDataFrame(
                geometry=pd.Series(
                    gdf.geometry.apply(geometry_to_multilinestring).explode().apply(explode_linestring)
                ).explode(ignore_index=True),
                crs=gdf.crs,
            )
            splitters_lines.geometry = splitters_lines.geometry.centroid.buffer(0.1, resolution=1)
            roads["new_geometry"] = (
                roads.geometry.apply(geometry_to_multilinestring).explode().apply(explode_linestring)
            )
            roads = roads.explode(column="new_geometry", ignore_index=True)
            roads["geometry"] = roads["new_geometry"]
            roads.drop(columns=["new_geometry"], inplace=True)
            roads = roads.sjoin(splitters_lines, how="inner", predicate="intersects")
            roads = roads[~roads.index.duplicated(keep="first")]
            local_road_width = roads_width_def.get("local road")
            if "roads_width" not in roads.columns:
                logger.warning(
                    f"Column 'roads_width' missing in GeoDataFrame, filling it with default local road width {local_road_width}"
                )
                roads["roads_width"] = local_road_width
            roads["roads_width"] = roads["roads_width"].fillna(local_road_width)
            roads["road_lvl"] = "user_roads"

        gdf.geometry = gdf.geometry.apply(patch_polygon_interior)
        self.user_valid_roads = roads
        self.source_multipolygon = False if len(gdf) == 1 else True
        self.territory_to_work_with = gdf

    def _run(self, initial_func, *args, **kwargs):
        task_queue = multiprocessing.Queue()
        kwargs.update({"dev_mod": self.dev_mod})
        task_queue.put((initial_func, args, kwargs))
        res, roads = parallel_split_queue(task_queue, self.local_crs, dev=self.dev_mod)

        roads = pd.concat([roads, self.user_valid_roads], ignore_index=True)
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
        return res.to_crs(self.original_crs), roads.to_crs(self.original_crs)

    def _check_fixed_zones(self, zones_ratio_dict: dict, fixed_zones: gpd.GeoDataFrame) -> gpd.GeoDataFrame:

        if not (fixed_zones.geom_type == "Point").all():
            raise TypeError("All geometries in fixed_zones must be of type 'Point'.")

        if "fixed_zone" not in fixed_zones.columns:
            raise KeyError("Column 'fixed_zone' is missing in the GeoDataFrame.")

        fixed_zone_values = set(fixed_zones["fixed_zone"])
        valid_zone_keys = set(zones_ratio_dict.keys())
        invalid_zones = fixed_zone_values - valid_zone_keys

        if invalid_zones:
            raise ValueError(
                f"The following fixed_zone values are not present in zones_ratio_dict: {invalid_zones}\n"
                f"Available keys in zones_ratio_dict: {valid_zone_keys}\n"
                f"Provided fixed_zone values: {fixed_zone_values}"
            )
        fixed_zones = fixed_zones.to_crs(self.local_crs)
        joined = gpd.sjoin(fixed_zones, self.territory_to_work_with, how="left", predicate="within")
        if joined["index_right"].isna().any():
            raise ValueError("Some points in fixed_zones are located outside the working territory geometries.")

        return fixed_zones

    def split_features(
        self, zones_ratio_dict: dict = None, zones_n: int = None, roads_width=None, fixed_zones: gpd.GeoDataFrame = None
    ):
        """
        Splits every feature in working gdf according to provided zones_ratio_dict or zones_n
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
            fixed_zones = self._check_fixed_zones(zones_ratio_dict, fixed_zones)
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

    def features2terr_zones(
        self, funczone: FuncZone = basic_func_zone, fixed_terr_zones: gpd.GeoDataFrame = None
    ) -> (gpd.GeoDataFrame, gpd.GeoDataFrame):
        return self._features2terr_zones(funczone, fixed_terr_zones, split_further=False)

    def features2terr_zones2blocks(
        self, funczone: FuncZone = basic_func_zone, fixed_terr_zones: gpd.GeoDataFrame = None
    ) -> (gpd.GeoDataFrame, gpd.GeoDataFrame):
        return self._features2terr_zones(funczone, fixed_terr_zones, split_further=True)

    def _features2terr_zones(
        self, funczone: FuncZone = basic_func_zone, fixed_terr_zones: gpd.GeoDataFrame = None, split_further=False
    ) -> (gpd.GeoDataFrame, gpd.GeoDataFrame):
        if not isinstance(funczone, FuncZone):
            raise TypeError("funczone arg must be of type FuncZone")
        if fixed_terr_zones is not None:
            fixed_terr_zones = self._check_fixed_zones(funczone.zones_ratio, fixed_terr_zones)

        args = self.territory_to_work_with, funczone, split_further, fixed_terr_zones

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
