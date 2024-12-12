import geopandas as gpd
import numpy as np
import pandas as pd

from app.gen_planner.python.src.tasks.splitters import _split_polygon, zone2block_splitter

from app.gen_planner.python.src._config import config

poisson_n_radius = config.poisson_n_radius.copy()
roads_width_def = config.roads_width_def.copy()

def terr2district2zone2block_initial(task, **kwargs):
    territory, genplan = task
    areas_dict = genplan.func_zone_ratio
    # raise RuntimeError(territory.area, genplan.min_zone_area)
    local_crs = kwargs.get("local_crs")
    zones, roads = _split_polygon(
        polygon=territory,
        areas_dict=areas_dict,
        point_radius=poisson_n_radius.get(len(areas_dict), 0.1),
        local_crs=local_crs,
    )
    road_lvl = "high speed highway"
    roads["road_lvl"] = road_lvl
    roads['roads_width'] = roads_width_def.get('high speed highway')
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
    road_lvl = "regulated highway"
    roads["road_lvl"] = road_lvl
    roads['roads_width'] = roads_width_def.get('regulated highway')
    tasks = []
    kwargs.update({"func_zone": func_zone.name})

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
        return [(zone2block_splitter, (zone_to_split, [1], min_area, 1, [roads_width_def.get('local road')]),
                 kwargs)], True, gpd.GeoDataFrame()

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
    roads_widths = np.linspace(int(roads_width_def.get('regulated highway') * 0.66), roads_width_def.get('local road'),
                               len(delimeters))
    return [
        (zone2block_splitter, (zone_to_split, delimeters, min_area, 1, roads_widths), kwargs)], True, gpd.GeoDataFrame()

