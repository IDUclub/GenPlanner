import geopandas as gpd
import numpy as np
import pandas as pd
from shapely import LineString

from app.gen_planner.python.src._config import config
from app.gen_planner.python.src.tasks.splitters import _split_polygon, poly2block_splitter
from app.gen_planner.python.src.utils import elastic_wrap

poisson_n_radius = config.poisson_n_radius.copy()
roads_width_def = config.roads_width_def.copy()


def poly2func2terr2block_initial(task, **kwargs):
    territory, genplan, split_further = task
    areas_dict = genplan.func_zone_ratio
    local_crs = kwargs.get("local_crs")
    zones, roads = _split_polygon(
        polygon=territory,
        areas_dict=areas_dict,
        point_radius=poisson_n_radius.get(len(areas_dict), 0.1),
        local_crs=local_crs,
    )
    road_lvl = "high speed highway"
    roads["road_lvl"] = road_lvl
    roads["roads_width"] = roads_width_def.get("high speed highway")
    if not split_further:
        zones["gen_plan"] = genplan.name
        zones["func_zone"] = zones["zone_name"].apply(lambda x: x.name)
        zones = zones[["gen_plan", "func_zone", "geometry"]]
        return zones, False, roads

    tasks = []
    kwargs.update({"gen_plan": genplan.name})
    for _, zone in zones.iterrows():
        tasks.append((poly2terr2block_initial, (zone.geometry, zone.zone_name, True), kwargs))
    return tasks, True, roads


def multipoly2terr2block_initial(task, **kwargs):
    multiterritory, funczone, split_further = task
    areas_dict = funczone.zones_ratio
    local_crs = kwargs.get("local_crs")

    territory = elastic_wrap(gpd.GeoDataFrame(geometry=[multiterritory],crs=local_crs))
    # return gpd.GeoDataFrame(geometry=[territory],crs=local_crs), False, gpd.GeoDataFrame(data =[1],geometry=[LineString(territory.exterior)],columns=['roads_width'],crs=local_crs)
    zones, roads = _split_polygon(
        polygon=territory,
        areas_dict=areas_dict,
        point_radius=poisson_n_radius.get(len(areas_dict), 0.1),
        local_crs=local_crs,
    )
    roads["roads_width"] = 10
    return zones, False, roads

def poly2terr2block_initial(task, **kwargs):
    poly, func_zone, split_further = task

    def recalculate_ratio(data, area):
        data["ratio"] = data["ratio"] / data["ratio"].sum()
        data["required_area"] = area * data["ratio"]
        data["good"] = data["min_block_area"] < data["required_area"]
        return data

    local_crs = kwargs.get("local_crs")
    area = poly.area
    terr_zones = pd.DataFrame.from_dict(
        {terr_zone: [ratio, terr_zone.min_block_area] for terr_zone, ratio in func_zone.zones_ratio.items()},
        orient="index",
        columns=["ratio", "min_block_area"],
    )

    terr_zones = recalculate_ratio(terr_zones, area)
    while not terr_zones["good"].all():
        terr_zones = terr_zones[terr_zones["good"]].copy()
        terr_zones = recalculate_ratio(terr_zones, area)

    if len(terr_zones) == 0:
        profile_terr = max(func_zone.zones_ratio.items(), key=lambda x: x[1])[0]
        data = {"terr_zone": [profile_terr.name], "func_zone": [func_zone.name], "geometry": [poly]}
        return gpd.GeoDataFrame(data=data, geometry="geometry", crs=kwargs.get("local_crs")), False, gpd.GeoDataFrame()

    zones, roads = _split_polygon(
        polygon=poly,
        areas_dict=terr_zones["ratio"].to_dict(),
        point_radius=poisson_n_radius.get(len(terr_zones), 0.1),
        local_crs=local_crs,
    )
    road_lvl = "regulated highway"
    roads["road_lvl"] = road_lvl
    roads["roads_width"] = roads_width_def.get("regulated highway")

    if not split_further:
        zones["func_zone"] = func_zone.name
        zones["terr_zone"] = zones["zone_name"].apply(lambda x: x.name)
        zones = zones[["func_zone", "terr_zone", "geometry"]]
        return zones, False, roads

    tasks = []
    kwargs.update({"func_zone": func_zone.name})

    for _, zone in zones.iterrows():
        tasks.append((poly2block_initial, (zone.geometry, zone.zone_name), kwargs))
    return tasks, True, roads


def poly2block_initial(task, **kwargs):
    poly, terr_zone = task
    kwargs.update({"terr_zone": terr_zone.name})
    target_area = poly.area
    min_area = terr_zone.min_block_area
    max_delimeter = 6
    temp_area = min_area
    delimeters = []
    while temp_area < target_area:
        temp_area = temp_area * max_delimeter
        delimeters.append(max_delimeter)
    if len(delimeters) == 0:
        return (
            [(poly2block_splitter, (poly, [1], min_area, 1, [roads_width_def.get("local road")]), kwargs)],
            True,
            gpd.GeoDataFrame(),
        )

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
    roads_widths = np.linspace(
        int(roads_width_def.get("regulated highway") * 0.66), roads_width_def.get("local road"), len(delimeters)
    )
    return (
        [(poly2block_splitter, (poly, delimeters, min_area, 1, roads_widths), kwargs)],
        True,
        gpd.GeoDataFrame(),
    )
