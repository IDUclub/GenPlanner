import geopandas as gpd
import pandas as pd
import pulp
from loguru import logger
from shapely import LineString, Polygon, Point
from shapely.ops import polygonize, unary_union, nearest_points

from app.gen_planner.python.src._config import config
from app.gen_planner.python.src.tasks.base_splitters import _split_polygon
from app.gen_planner.python.src.tasks.block_splitters import multi_feature2blocks_initial
from app.gen_planner.python.src.utils import (
    polygon_angle,
    rotate_coords,
    elastic_wrap,
    geometry_to_multilinestring,
)
from app.gen_planner.python.src.zoning import FuncZone

poisson_n_radius = config.poisson_n_radius.copy()
roads_width_def = config.roads_width_def.copy()


def filter_terr_zone(terr_zones: pd.DataFrame, area) -> pd.DataFrame:
    def recalculate_ratio(data, area):
        data["ratio"] = data["ratio"] / data["ratio"].sum()
        data["required_area"] = area * data["ratio"]
        data["good"] = (data["min_block_area"] * 0.8) < data["required_area"]
        return data

    terr_zones = recalculate_ratio(terr_zones, area)
    while not terr_zones["good"].all():
        terr_zones = terr_zones[terr_zones["good"]].copy()
        logger.debug(f"removed terr_zones {terr_zones[~terr_zones['good']]}")
        terr_zones = recalculate_ratio(terr_zones, area)
    return terr_zones


def multi_feature2terr_zones_initial(task, **kwargs):
    initial_gdf, func_zone, split_further, fixed_terr_zones = task
    local_crs = initial_gdf.crs
    initial_gdf["feature_area"] = initial_gdf.area
    # TODO split gdf on parts with pulp if too big for 1 func_zone

    territory_union = elastic_wrap(initial_gdf)
    # TODO simplify territory_union based on area, better performance

    terr_zones = pd.DataFrame.from_dict(
        {terr_zone: [ratio, terr_zone.min_block_area] for terr_zone, ratio in func_zone.zones_ratio.items()},
        orient="index",
        columns=["ratio", "min_block_area"],
    )
    terr_zones = filter_terr_zone(terr_zones, initial_gdf["feature_area"].sum())

    pivot_point = territory_union.centroid
    angle_rad_to_rotate = polygon_angle(territory_union)

    if fixed_terr_zones is None:
        fixed_terr_zones = gpd.GeoDataFrame()

    if len(fixed_terr_zones) > 0:
        fixed_zones_in_poly = fixed_terr_zones[fixed_terr_zones.within(territory_union)].copy()
        if len(fixed_zones_in_poly) > 0:
            fixed_zones_in_poly["geometry"] = fixed_zones_in_poly["geometry"].apply(
                lambda x: Point(rotate_coords(x.coords, pivot_point, -angle_rad_to_rotate))
            )
            fixed_zones_in_poly["zone_name"] = fixed_zones_in_poly["fixed_zone"].apply(lambda x: x.name)
            fixed_zones_in_poly = fixed_zones_in_poly.groupby("zone_name", as_index=False).agg(
                {"geometry": list, "fixed_zone": "first"}
            )
            fixed_zones_in_poly = fixed_zones_in_poly.set_index("fixed_zone")["geometry"].to_dict()
        else:
            fixed_zones_in_poly = None
    else:
        fixed_zones_in_poly = None

    territory_union = Polygon(rotate_coords(territory_union.exterior.coords, pivot_point, -angle_rad_to_rotate))

    proxy_zones, _ = _split_polygon(
        polygon=territory_union,
        areas_dict=terr_zones["ratio"].to_dict(),
        point_radius=poisson_n_radius.get(len(terr_zones), 0.1),
        local_crs=local_crs,
        fixed_zone_points=fixed_zones_in_poly,
    )

    # Разворачиваем прокси зоны обратно
    if not proxy_zones.empty:
        proxy_zones.geometry = proxy_zones.geometry.apply(
            lambda geom: Polygon(rotate_coords(geom.exterior.coords, pivot_point, angle_rad_to_rotate))
        )

    proxy_fix_points = proxy_zones.copy()
    proxy_fix_points.geometry = proxy_fix_points.geometry.centroid
    if len(fixed_terr_zones) > 0:
        proxy_fix_points = proxy_fix_points.merge(
            fixed_terr_zones, left_on="zone_name", right_on="fixed_zone", how="left", suffixes=("", "_fixed")
        )
        proxy_fix_points["geometry"] = proxy_fix_points["geometry_fixed"].combine_first(proxy_fix_points["geometry"])
        proxy_fix_points = proxy_fix_points.drop(columns=["geometry_fixed", "fixed_zone", "ratio"])

    lines_orig = initial_gdf.geometry.apply(geometry_to_multilinestring).to_list()
    lines_new = proxy_zones.geometry.apply(geometry_to_multilinestring).to_list()

    proxy_polygons = gpd.GeoDataFrame(
        geometry=list(polygonize(unary_union(lines_orig + lines_new))), crs=local_crs
    ).explode(index_parts=False)

    del lines_orig, lines_new

    proxy_polygons.geometry = proxy_polygons.representative_point()
    proxy_polygons = proxy_polygons.sjoin(proxy_zones, how="inner", predicate="within").drop(columns="index_right")
    division = initial_gdf.sjoin(proxy_polygons, how="inner", predicate="intersects")
    del proxy_polygons, proxy_zones
    division["zone_to_add"] = division["zone_name"].apply(lambda terr: terr.name)
    division = (
        division.reset_index()
        .groupby(["index", "zone_to_add"], as_index=False)
        .agg({"feature_area": "first", "zone_name": "first", "geometry": "first"})
    )

    terr_zones = terr_zones.reset_index(names="zone")
    terr_zones["zone"] = terr_zones["zone"].apply(lambda x: x.name)

    terr_zones["required_area"] = terr_zones["required_area"] * 0.999

    zone_capacity = division.groupby("index")["feature_area"].first().to_dict()
    zone_permitted = set(division[["index", "zone_to_add"]].itertuples(index=False, name=None))
    min_areas = terr_zones.set_index("zone")["min_block_area"].to_dict()
    target_areas = terr_zones.set_index("zone")["required_area"].to_dict()

    model = pulp.LpProblem("Territorial_Zoning", pulp.LpMinimize)

    x = {(i, z): pulp.LpVariable(f"feature index {i} zone type {z}", lowBound=0) for (i, z) in zone_permitted}
    y = {(i, z): pulp.LpVariable(f"y_{i}_{z}", cat="Binary") for (i, z) in zone_permitted}

    slack = {(i, z): pulp.LpVariable(f"slack_{i}_{z}", lowBound=0) for (i, z) in x}

    for i in division["index"].unique():
        model += (
            pulp.lpSum(x[i, z] for z in terr_zones["zone"] if (i, z) in x) <= zone_capacity[i],
            f"Capacity_feature_{i}",
        )
    for i, z in x:
        model += x[i, z] + slack[i, z] >= min_areas[z] * y[i, z], f"SoftMinArea_{i}_{z}"
        model += x[i, z] <= zone_capacity[i] * y[i, z], f"MaxIfAssigned_{i}_{z}"

    for z in terr_zones["zone"]:
        model += (
            pulp.lpSum(x[i, z] for i in division["index"].unique() if (i, z) in x) >= target_areas[z],
            f"TargetArea_{z}",
        )
    # TODO добавить запрет на нулевые зоны

    if len(fixed_terr_zones) > 0:
        fixed_terr_zones["zone_name"] = fixed_terr_zones["fixed_zone"].apply(lambda x: x.name)
        zone_strongly_fixed = set(initial_gdf.sjoin(fixed_terr_zones)[["zone_name"]].itertuples(name=None))
        for i, z in zone_strongly_fixed:
            if (i, z) in x:
                model += x[i, z] >= 1e-3, f"StronglyFixed_{i}_{z}"

    model += pulp.lpSum(slack[i, z] for (i, z) in slack), "MinimizeTotalSlack"

    model.solve(pulp.PULP_CBC_CMD(msg=True, timeLimit=20, gapRel=0.02))
    print("Статус:", pulp.LpStatus[model.status])

    del zone_capacity, zone_permitted, min_areas, target_areas, division, model, slack

    allocations = []
    for (i, z), var in x.items():
        val = var.varValue
        if val and val > 0:
            allocations.append((i, z, round(val, 2)))
    del x, y
    allocations = pd.DataFrame(allocations, columns=["zone_index", "territorial_zone", "assigned_area"])
    kwargs.update({"func_zone": func_zone.name})

    ready_for_blocks = []
    new_tasks = []

    for ind, zone_row in initial_gdf.loc[allocations["zone_index"].unique()].iterrows():
        zone_polygon = zone_row.geometry
        terr_zones_in_poly = allocations[allocations["zone_index"] == ind].copy()
        terr_zones_in_poly = terr_zones_in_poly[terr_zones_in_poly["assigned_area"] > 0]
        if len(terr_zones_in_poly) == 1:
            # Отправляем на генерацию кварталов / финальный результат
            terr_zone_str = terr_zones_in_poly.iloc[0]["territorial_zone"]
            terr_zone = func_zone.zones_keys[terr_zone_str]
            ready_for_blocks.append(
                gpd.GeoDataFrame(geometry=[zone_polygon], data=[terr_zone], columns=["territory_zone"], crs=local_crs)
            )
        elif len(terr_zones_in_poly) > 1:
            zone_area_total = zone_row["feature_area"]
            zones_ratio_dict = {
                func_zone.zones_keys[row["territorial_zone"]]: row["assigned_area"] / zone_area_total
                for _, row in terr_zones_in_poly.iterrows()
            }

            task_gdf = gpd.GeoDataFrame(geometry=[zone_polygon], crs=local_crs)
            task_func_zone = FuncZone(zones_ratio_dict, name=func_zone.name)
            task_fixed_terr_zones = proxy_fix_points[
                proxy_fix_points["zone_name"].isin(list(zones_ratio_dict.keys()))
            ].copy()
            task_fixed_terr_zones.rename(columns={"zone_name": "fixed_zone"}, inplace=True)
            task_fixed_terr_zones["geometry"] = task_fixed_terr_zones["geometry"].apply(
                lambda fix_p: nearest_points(fix_p, zone_polygon.buffer(-0.1, resolution=1))[1]
            )
            # task_fixed_terr_zones = None
            new_tasks.append(
                (feature2terr_zones_initial, (task_gdf, task_func_zone, split_further, task_fixed_terr_zones), kwargs)
            )
    if len(ready_for_blocks) > 0:
        block_splitter_gdf = pd.concat(ready_for_blocks)
    else:
        block_splitter_gdf = gpd.GeoDataFrame()

    if split_further:
        if len(block_splitter_gdf) > 0:
            new_tasks.append((multi_feature2blocks_initial, (block_splitter_gdf,), kwargs))
        return {"new_tasks": new_tasks}

        # return {"new_tasks": new_tasks,"generation":proxy_generation}
    else:
        if len(block_splitter_gdf) > 0:
            block_splitter_gdf["func_zone"] = func_zone
        # block_splitter_gdf["territory_zone"] = block_splitter_gdf["territory_zone"].apply(lambda x: x.name)
        return {"new_tasks": new_tasks, "generation": block_splitter_gdf}

        # return {"new_tasks": new_tasks, "generation": pd.concat([block_splitter_gdf,proxy_generation],ignore_index=True)}


def feature2terr_zones_initial(task, **kwargs):
    gdf, func_zone, split_further, fixed_terr_zones = task

    # TODO split gdf on parts if too big for 1 funczone

    polygon = gdf.iloc[0].geometry
    local_crs = gdf.crs
    area = polygon.area

    terr_zones = pd.DataFrame.from_dict(
        {terr_zone: [ratio, terr_zone.min_block_area] for terr_zone, ratio in func_zone.zones_ratio.items()},
        orient="index",
        columns=["ratio", "min_block_area"],
    )

    terr_zones = filter_terr_zone(terr_zones, area)

    if len(terr_zones) == 0:
        profile_terr = max(func_zone.zones_ratio.items(), key=lambda x: x[1])[0]
        data = {"territory_zone": [profile_terr], "func_zone": [func_zone], "geometry": [polygon]}
        return {"generation": gpd.GeoDataFrame(data=data, geometry="geometry", crs=local_crs)}

    pivot_point = polygon.centroid
    angle_rad_to_rotate = polygon_angle(polygon)

    if fixed_terr_zones is None:
        fixed_terr_zones = gpd.GeoDataFrame()

    if len(fixed_terr_zones) > 0:
        fixed_zones_in_poly = fixed_terr_zones[fixed_terr_zones.intersects(polygon)].copy()
        if len(fixed_zones_in_poly) > 0:
            fixed_zones_in_poly["geometry"] = fixed_zones_in_poly["geometry"].apply(
                lambda x: Point(rotate_coords(x.coords, pivot_point, -angle_rad_to_rotate))
            )
            fixed_zones_in_poly["zone_name"] = fixed_zones_in_poly["fixed_zone"].apply(lambda x: x.name)
            fixed_zones_in_poly = fixed_zones_in_poly.groupby("zone_name", as_index=False).agg(
                {"geometry": list, "fixed_zone": "first"}
            )
            fixed_zones_in_poly = fixed_zones_in_poly.set_index("fixed_zone")["geometry"].to_dict()
        else:
            fixed_zones_in_poly = None
    else:
        fixed_zones_in_poly = None

    polygon = Polygon(rotate_coords(polygon.exterior.coords, pivot_point, -angle_rad_to_rotate))

    zones, roads = _split_polygon(
        polygon=polygon,
        areas_dict=terr_zones["ratio"].to_dict(),
        point_radius=poisson_n_radius.get(len(terr_zones), 0.1),
        local_crs=local_crs,
        fixed_zone_points=fixed_zones_in_poly,
    )

    if not zones.empty:
        zones.geometry = zones.geometry.apply(
            lambda x: Polygon(rotate_coords(x.exterior.coords, pivot_point, angle_rad_to_rotate))
        )
    if not roads.empty:
        roads.geometry = roads.geometry.apply(
            lambda x: LineString(rotate_coords(x.coords, pivot_point, angle_rad_to_rotate))
        )

    road_lvl = "regulated highway"
    roads["road_lvl"] = road_lvl
    roads["roads_width"] = roads_width_def.get("regulated highway")

    if not split_further:
        zones["func_zone"] = func_zone
        zones["territory_zone"] = zones["zone_name"]
        zones = zones[["func_zone", "territory_zone", "geometry"]]
        return {"generation": zones, "generated_roads": roads}

    # if split further
    kwargs.update({"func_zone": func_zone.name})
    zones["territory_zone"] = zones["zone_name"]
    task = [(multi_feature2blocks_initial, (zones,), kwargs)]
    return {"new_tasks": task, "generated_roads": roads}
