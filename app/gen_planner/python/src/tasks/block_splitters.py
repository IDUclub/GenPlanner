import geopandas as gpd
import numpy as np
from shapely import LineString, Polygon

from app.gen_planner.python.src._config import config
from app.gen_planner.python.src.tasks.base_splitters import _split_polygon
from app.gen_planner.python.src.utils import (
    polygon_angle,
    rotate_coords,
)

poisson_n_radius = config.poisson_n_radius.copy()
roads_width_def = config.roads_width_def.copy()


def multi_feature2blocks_initial(task, **kwargs):
    (poly_gdf,) = task
    if not isinstance(poly_gdf, gpd.GeoDataFrame):
        raise ValueError(f"poly_gdf wrong dtype {type(poly_gdf)}")
    if "territory_zone" not in poly_gdf.columns:
        raise KeyError(f"territory_zone not in poly_gdf")
    kwargs.update({"local_crs": poly_gdf.crs})
    new_tasks = []
    for ind, row in poly_gdf.iterrows():

        zone_kwargs = kwargs.copy()
        zone_kwargs.update({"territory_zone": row.territory_zone})

        # TODO тут каким то образом может прийти геомка без territory zone, так и не отловил почему так
        geometry = row.geometry
        target_area = geometry.area
        min_block_area = row.territory_zone.min_block_area

        max_delimiter = 6
        temp_area = min_block_area
        delimiters = []

        # Ищем максимальную площадь больше чем таргет
        while temp_area < target_area:
            temp_area *= max_delimiter
            delimiters.append(max_delimiter)

        if len(delimiters) == 0:
            new_tasks.append(
                (
                    polygon2blocks_splitter,
                    (geometry, [1], min_block_area, 1, [roads_width_def.get("local road")]),
                    zone_kwargs,
                )
            )
            continue

        min_split = 1 if len(delimiters) == 1 else 2
        i = 0
        # Убираем деления, пока не приблизимся к площади
        while temp_area > target_area:
            if delimiters[i] > min_split:
                delimiters[i] -= 1
            else:
                i += 1
            temp_area = min_block_area * np.prod(delimiters)
        # Возвращаем последнее удаление
        delimiters[i] += 1

        min_width = int(roads_width_def.get("regulated highway") * 0.66)
        max_width = roads_width_def.get("local road")
        roads_widths = np.linspace(min_width, max_width, len(delimiters))

        # Добавление задачи
        new_tasks.append(
            (polygon2blocks_splitter, (geometry, delimiters, min_block_area, 1, roads_widths), zone_kwargs)
        )
    return {"new_tasks": new_tasks}


def polygon2blocks_splitter(task, **kwargs):
    polygon, delimeters, min_area, deep, roads_widths = task

    if deep == len(delimeters):
        n_areas = min(6, int(polygon.area // min_area))
    else:
        n_areas = delimeters[deep - 1]
        n_areas = min(n_areas, int(polygon.area // min_area))

    if n_areas in [0, 1]:
        data = {key: [value] for key, value in kwargs.items() if key in ["territory_zone", "func_zone", "gen_plan"]}
        blocks = gpd.GeoDataFrame(data=data, geometry=[polygon], crs=kwargs.get("local_crs"))
        return {"generation": blocks}

    areas_dict = {x: 1 / n_areas for x in range(n_areas)}

    pivot_point = polygon.centroid
    angle_rad_to_rotate = polygon_angle(polygon)
    polygon = Polygon(rotate_coords(polygon.exterior.coords, pivot_point, -angle_rad_to_rotate))
    blocks, roads = _split_polygon(
        polygon=polygon,
        areas_dict=areas_dict,
        point_radius=poisson_n_radius.get(n_areas, 0.1),
        local_crs=kwargs.get("local_crs"),
    )
    if not blocks.empty:
        blocks.geometry = blocks.geometry.apply(
            lambda x: Polygon(rotate_coords(x.exterior.coords, pivot_point, angle_rad_to_rotate))
        )
    if not roads.empty:
        roads.geometry = roads.geometry.apply(
            lambda x: LineString(rotate_coords(x.coords, pivot_point, angle_rad_to_rotate))
        )
    road_lvl = "local road"
    roads["road_lvl"] = f"{road_lvl}, level {deep}"
    roads["roads_width"] = roads_widths[deep - 1]
    if deep == len(delimeters):
        data = {
            key: [value] * len(blocks)
            for key, value in kwargs.items()
            if key in ["territory_zone", "func_zone", "gen_plan"]
        }
        blocks = gpd.GeoDataFrame(data=data, geometry=blocks.geometry, crs=kwargs.get("local_crs"))
        return {"generation": blocks, "generated_roads": roads}
    else:
        deep = deep + 1
        blocks = blocks.geometry
        tasks = []
        for poly in blocks:
            if poly is not None:
                tasks.append(
                    (polygon2blocks_splitter, (Polygon(poly), delimeters, min_area, deep, roads_widths), kwargs)
                )

        return {"new_tasks": tasks, "generated_roads": roads}
