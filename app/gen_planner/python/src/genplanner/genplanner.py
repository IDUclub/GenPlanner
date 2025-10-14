import concurrent.futures
import multiprocessing
import time

import geopandas as gpd
import pandas as pd
from loguru import logger
from pyproj import CRS
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import polygonize, nearest_points, unary_union

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

    def __init__(
            self,
            features: gpd.GeoDataFrame,
            roads: gpd.GeoDataFrame = None,
            exclude_features: gpd.GeoDataFrame = None,
            existing_terr_zones: gpd.GeoDataFrame = None,
            existing_tz_fill_ratio: float = 0.8,
            simplify_geometry: bool = True,
            simplify_value=1,
            parallel=True
    ):
        self.original_territory = features.copy()
        self.original_crs = features.crs
        self.local_crs = features.estimate_utm_crs()
        self.existing_terr_zones = gpd.GeoDataFrame()
        self.static_fix_points = gpd.GeoDataFrame()
        self.territory_to_work_with = gpd.GeoDataFrame()

        if roads is None:
            roads = gpd.GeoDataFrame()
        if exclude_features is None:
            exclude_features = gpd.GeoDataFrame()
        if existing_terr_zones is None:
            existing_terr_zones = gpd.GeoDataFrame()

        self._create_working_gdf(
            self.original_territory.copy(),
            roads.copy(),
            exclude_features.copy(),
            existing_terr_zones.copy(),
            simplify_geometry,
            simplify_value,
            existing_tz_fill_ratio
        )

        self.dev_mod = not parallel
        if self.dev_mod:
            logger.info("Dev mod activated, no more ProcessPool")

    def _create_working_gdf(
            self,
            gdf: gpd.GeoDataFrame,
            roads: gpd.GeoDataFrame,
            exclude_features: gpd.GeoDataFrame,
            existing_terr_zones: gpd.GeoDataFrame,
            simplify_geometry: bool,
            simplify_value: float,
            existing_tz_fill_ratio: float
    ) -> Polygon | MultiPolygon:

        gdf = gdf[gdf.geom_type.isin(["MultiPolygon", "Polygon"])]

        if len(gdf) == 0:
            raise TypeError("No valid geometries in provided GeoDataFrame")

        gdf = gdf.to_crs(self.local_crs)
        gdf = gdf.explode(ignore_index=True)

        if len(exclude_features) > 0:
            exclude_features = exclude_features.to_crs(self.local_crs)
            exclude_features = exclude_features.clip(self.original_territory.to_crs(self.local_crs),
                                                     keep_geom_type=True)
            exclude_features.geometry = exclude_features.geometry.buffer(1, resolution=2)
            exclude_features = gpd.GeoDataFrame(geometry=[exclude_features.union_all()], crs=exclude_features.crs)
            if simplify_geometry:
                exclude_features.geometry = exclude_features.geometry.simplify(simplify_value)
            gdf = territory_splitter(gdf, exclude_features, return_splitters=False).reset_index(drop=True)

        if len(roads) > 0:
            roads = roads.to_crs(self.local_crs)
            roads = roads.explode(ignore_index=True)
            if simplify_geometry:
                roads.geometry = roads.geometry.simplify(simplify_value)
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

        if len(existing_terr_zones) > 0:
            if 'terr_zone' not in existing_terr_zones.columns:
                raise AttributeError(
                    '`terr_zone` column not found in GeoDataFrame, but existing_terr_zones was provided')

            existing_terr_zones = existing_terr_zones.to_crs(self.local_crs)
            existing_terr_zones = existing_terr_zones.clip(gdf, keep_geom_type=True)
            if simplify_geometry:
                existing_terr_zones.geometry = existing_terr_zones.geometry.simplify(simplify_value)

            splitted_territory = territory_splitter(gdf, existing_terr_zones, return_splitters=True).reset_index(
                drop=True)

            splitted_territory['existing_area'] = splitted_territory.area
            splitted_territory.geometry = splitted_territory.representative_point()
            splitted_territory = splitted_territory.sjoin(existing_terr_zones, how='left').rename(
                columns={'index_right': 'existing_zone_index'})
            splitted_territory = splitted_territory[~splitted_territory['terr_zone'].isna()]

            gdf['full_area'] = gdf.area
            potential = gdf.sjoin(splitted_territory, how='left')
            potential = potential[~potential['terr_zone'].isna()]
            potential['ratio'] = (potential['existing_area'] / potential['full_area']).round(2)
            consistent_idx = (
                potential.groupby(level=0)["terr_zone"]
                .nunique()
                .pipe(lambda s: s[s == 1].index)
            )
            potential = potential.loc[consistent_idx]
            potential: gpd.GeoDataFrame = potential[(potential['ratio'] >= existing_tz_fill_ratio)]

            for ezi, group in potential.groupby('existing_zone_index'):
                base = existing_terr_zones.at[ezi, "geometry"]
                merged = unary_union([base, *group.geometry.dropna().to_list()])
                existing_terr_zones.at[ezi, "geometry"] = merged

            existing_terr_zones['area'] = existing_terr_zones.geometry.area

            # TODO вырезать exclude_objects из existing_terr_zones
            self.existing_terr_zones = existing_terr_zones
            gdf = territory_splitter(gdf, existing_terr_zones, return_splitters=False).reset_index(drop=True)

        # if simplify_geometry:
        #     gdf.geometry = gdf.geometry.simplify(simplify_value)

        if len(existing_terr_zones) > 0:
            target = gdf.geometry.buffer(-0.1, resolution=1)
            target_boundary = target.boundary.union_all()
            fix_points = existing_terr_zones.copy()
            fix_points["__area__"] = fix_points.geometry.area
            fix_points = fix_points.sort_values(["terr_zone", "__area__"], ascending=[True, False])
            fix_points = fix_points.drop_duplicates(subset=["terr_zone"], keep="first")

            fix_points.geometry = existing_terr_zones.geometry.representative_point().apply(
                lambda p: nearest_points(p, target_boundary)[1]
            )
            fix_points = fix_points[['terr_zone', 'geometry']].rename(columns={'terr_zone': 'fixed_zone'})
            self.static_fix_points = fix_points

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

    def _prepare_fixed_zones_and_balance_ratios(self, zones_ratio_dict: dict, fixed_zones: gpd.GeoDataFrame | None) -> \
            tuple[gpd.GeoDataFrame, dict]:

        if fixed_zones is None:
            fixed_zones = gpd.GeoDataFrame(columns=["geometry", "fixed_zone"], geometry="geometry", crs=self.local_crs)
        else:
            if "fixed_zone" not in fixed_zones.columns:
                raise KeyError("Column 'fixed_zone' is missing in the GeoDataFrame.")
            if not (fixed_zones.geom_type == "Point").all():
                raise TypeError("All geometries in fixed_zones must be of type 'Point'.")
            fixed_zones = fixed_zones.to_crs(self.local_crs)

        valid_zone_keys = set(zones_ratio_dict.keys())

        if len(self.static_fix_points) > 0:
            sfx = self.static_fix_points.copy()

            sfx = sfx[sfx["fixed_zone"].isin(valid_zone_keys)]

            if len(fixed_zones) > 0:
                existing_labels = set(fixed_zones["fixed_zone"])
                sfx = sfx[~sfx["fixed_zone"].isin(existing_labels)]
            if len(sfx) > 0:
                sfx_joined = gpd.sjoin(sfx, self.territory_to_work_with, how="left", predicate="within")
                sfx_joined = sfx_joined[~sfx_joined['index_right'].isna()]
                fixed_zones = pd.concat([fixed_zones, sfx_joined[["fixed_zone", "geometry"]]], ignore_index=True)

        fixed_zone_values = set(fixed_zones["fixed_zone"])
        invalid_zones = fixed_zone_values - valid_zone_keys

        if invalid_zones:
            raise ValueError(
                f"The following fixed_zone values are not present in zones_ratio_dict: {invalid_zones}\n"
                f"Available keys in zones_ratio_dict: {valid_zone_keys}\n"
                f"Provided fixed_zone values: {fixed_zone_values}"
            )
        if len(fixed_zones) > 0:
            fixed_zones = fixed_zones.to_crs(self.local_crs)
            joined = gpd.sjoin(fixed_zones, self.territory_to_work_with, how="left", predicate="within")
            if joined["index_right"].isna().any():
                raise ValueError("Some points in fixed_zones are located outside the working territory geometries.")

        if len(self.existing_terr_zones) > 0:
            pieces = list(self.territory_to_work_with.geometry) + list(self.existing_terr_zones.geometry)
            total_area = unary_union(pieces).area
            existing_ratios_by_zone: dict[str, float] = {}
            dissolved = self.existing_terr_zones.dissolve(by="terr_zone", as_index=False)
            dissolved["__area__"] = dissolved.geometry.area
            for _, row in dissolved.iterrows():
                z = row["terr_zone"]
                a = float(row["__area__"])
                existing_ratios_by_zone[z] = a / total_area
            balanced_ratio_dict = {}
            for z, target in zones_ratio_dict.items():
                existed = existing_ratios_by_zone.get(z, 0.0)
                remaining = max(float(target) - float(existed), 0.0)
                balanced_ratio_dict[z] = remaining
            zones_ratio_dict = balanced_ratio_dict
        return fixed_zones, zones_ratio_dict
        #

    def split_features(
            self, zones_ratio_dict: dict = None, zones_n: int = None, roads_width=None,
            fixed_zones: gpd.GeoDataFrame = None
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
            fixed_zones = self._prepare_fixed_zones_and_balance_ratios(zones_ratio_dict, fixed_zones)
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
            self, funczone: FuncZone, fixed_terr_zones: gpd.GeoDataFrame = None
    ) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:

        return self._features2terr_zones(funczone, fixed_terr_zones, split_further=True)

    def _features2terr_zones(
            self, funczone: FuncZone = basic_func_zone, fixed_terr_zones: gpd.GeoDataFrame = None, split_further=False
    ) -> (gpd.GeoDataFrame, gpd.GeoDataFrame):
        if not isinstance(funczone, FuncZone):
            raise TypeError("funczone arg must be of type FuncZone")
        updated_tz, updated_zr = self._prepare_fixed_zones_and_balance_ratios(funczone.zones_ratio, fixed_terr_zones)
        funczone.zones_ratio = updated_zr

        args = self.territory_to_work_with, funczone, split_further, updated_tz

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
