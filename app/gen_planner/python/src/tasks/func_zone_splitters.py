from app.gen_planner.python.src._config import config
from app.gen_planner.python.src.tasks.base_splitters import _split_polygon
from app.gen_planner.python.src.tasks.terr_zone_splitters import feature2terr_zones_initial

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
        tasks.append((feature2terr_zones_initial, (zone.geometry, zone.zone_name, True), kwargs))
    return tasks, True, roads
