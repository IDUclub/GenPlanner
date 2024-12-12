import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import CRS
from rust_optimizer import optimize_space
from shapely.geometry import Polygon, MultiPolygon, LineString

from gen_planner.python.src import (
    normalize_coords,
    denormalize_coords,
    generate_points,
)
from gen_planner.python.src import config

poisson_n_radius = config.poisson_n_radius.copy()

def zone2block_splitter(task, **kwargs):
    polygon, delimeters, min_area, deep, roads_widths = task
    if deep == len(delimeters):
        n_areas = min(8, int(polygon.area // min_area))
        if n_areas in [0, 1]:
            data = {key: [value] for key, value in kwargs.items() if key != "local_crs"}
            blocks = gpd.GeoDataFrame(data=data, geometry=[polygon], crs=kwargs.get("local_crs"))
            return blocks, False, gpd.GeoDataFrame()
    else:
        n_areas = delimeters[deep - 1]
        n_areas = min(n_areas, int(polygon.area // min_area))

    areas_dict = {x: 1 / n_areas for x in range(n_areas)}
    blocks, roads = _split_polygon(
        polygon=polygon,
        areas_dict=areas_dict,
        point_radius=poisson_n_radius.get(n_areas, 0.1),
        local_crs=kwargs.get("local_crs"),
        dev = True
    )

    road_lvl = "local road"
    roads["road_lvl"] = f"{road_lvl}, level {deep}"
    roads['roads_width'] = roads_widths[deep - 1]
    if deep == len(delimeters):
        data = {key: [value] * len(blocks) for key, value in kwargs.items() if key != "local_crs"}
        blocks = gpd.GeoDataFrame(data=data, geometry=blocks.geometry, crs=kwargs.get("local_crs"))
        return blocks, False, roads
    else:
        deep = deep + 1
        blocks = blocks.geometry
        tasks = []
        for poly in blocks:
            if poly is not None:
                tasks.append((zone2block_splitter, (Polygon(poly), delimeters, min_area, deep, roads_widths), kwargs))

        return tasks, True, roads


def _split_polygon(
        polygon: Polygon,
        areas_dict: dict,
        local_crs: CRS,
        point_radius: float = 0.1,
        zone_connections: list = None,
        dev = False,
) -> (gpd.GeoDataFrame, gpd.GeoDataFrame):

    if zone_connections is None:
        zone_connections = []

    def create_polygons(site2idx, site2room, idx2vtxv, vtxv2xy):
        poly_coords = []
        poly_sites = []
        for i_site in range(len(site2idx) - 1):
            if site2room[i_site] == np.iinfo(np.uint32).max:
                continue

            num_vtx_in_site = site2idx[i_site + 1] - site2idx[i_site]
            if num_vtx_in_site == 0:
                continue

            vtx2xy = []
            for i_vtx in range(num_vtx_in_site):  # collecting poly
                i_vtxv = idx2vtxv[site2idx[i_site] + i_vtx]  # founding vertex id
                vtx2xy.append((vtxv2xy[i_vtxv * 2], vtxv2xy[i_vtxv * 2 + 1]))  # adding vertex xy to poly
            poly_sites.append(site2room[i_site])
            poly_coords.append(Polygon(vtx2xy))

        return poly_coords, poly_sites

    bounds = polygon.bounds
    normalized_polygon = Polygon(normalize_coords(polygon.exterior.coords, bounds))
    attempts = 10

    for i in range(attempts):  # 10 attempts
        try:
            poisson_points = generate_points(normalized_polygon, point_radius)
            full_area = normalized_polygon.area
            areas = pd.DataFrame(list(areas_dict.items()), columns=["zone_name", "ratio"])

            areas["ratio"] = areas["ratio"] / areas["ratio"].sum()
            areas["area"] = areas["ratio"] * full_area

            areas["ratio_sqrt"] = np.sqrt(areas["ratio"]) / (sum(np.sqrt(areas["ratio"])))
            areas["area_sqrt"] = areas["ratio_sqrt"] * full_area

            area_per_site = areas["area_sqrt"].sum() / (len(poisson_points))
            areas["site_indeed"] = np.floor(areas["area_sqrt"] / area_per_site).astype(int)

            total_points_assigned = areas["site_indeed"].sum()
            points_difference = len(poisson_points) - total_points_assigned

            if points_difference > 0:  #
                for _ in range(points_difference):
                    areas.loc[areas["site_indeed"].idxmin(), "site_indeed"] += 1
            elif points_difference < 0:
                for _ in range(abs(points_difference)):
                    areas.loc[areas["site_indeed"].idxmax(), "site_indeed"] -= 1
            site2room = np.random.permutation(np.repeat(areas.index, areas["site_indeed"]))

            normalized_border = [
                round(item, 8)
                for sublist in normalized_polygon.exterior.segmentize(0.1).normalize().coords[::-1]
                for item in sublist
            ]

            res = optimize_space(
                vtxl2xy=normalized_border,
                site2xy=poisson_points.flatten().round(8).tolist(),
                site2room=site2room.tolist(),
                site2xy2flag=[0.0 for _ in range(len(site2room) * 2)],
                room2area_trg=areas["area"].sort_index().round(8).tolist(),
                room_connections=zone_connections,
                create_gif=False,
            )

            site2idx = res[0]  # number of points [0,5,10,15,20] means there are 4 polygons with indexes 0..5 etc
            idx2vtxv = res[1]  # node indexes for each voronoi poly
            vtxv2xy = res[2]  # all points from generation (+bounds)
            site2room = site2room.tolist()
            edge2vtxv_wall = res[3]  # complete walls/roads

            vtxv2xy = denormalize_coords(
                [coords for coords in np.array(vtxv2xy).reshape(int(len(vtxv2xy) / 2), 2)], bounds
            )

            polygons, poly_sites = create_polygons(site2idx, site2room, idx2vtxv, np.array(vtxv2xy).flatten().tolist())
            devided_zones = (
                gpd.GeoDataFrame(geometry=polygons, data=poly_sites, columns=["zone_id"], crs=local_crs)
                .dissolve("zone_id")
                .reset_index()
            )
            if len(devided_zones) != len(areas):
                raise ValueError(f"Number of devided_zones does not match {len(areas)}: {len(devided_zones)}")

            devided_zones = devided_zones.merge(areas.reset_index(), left_on="zone_id", right_on="index").drop(
                columns=["index", "area", "site_indeed", "zone_id"]
            )
            for geom in devided_zones.geometry:
                if isinstance(geom, MultiPolygon):
                    raise ValueError(f"MultiPolygon returned from optimizer. Have to recalculate.")

            new_area = devided_zones.area.sum()
            if new_area > polygon.area * 1.1 or new_area < polygon.area * 0.9:
                raise ValueError(f"Area of devided_zones does not match {new_area}:{polygon.area}")

            new_roads = [
                (vtxv2xy[x[0]], vtxv2xy[x[1]])
                for x in np.array(edge2vtxv_wall).reshape(int(len(edge2vtxv_wall) / 2), 2)
            ]
            new_roads = gpd.GeoDataFrame(geometry=[LineString(x) for x in new_roads], crs=local_crs)
            return devided_zones, new_roads

        except Exception as e:
            if i + 1 == attempts:

                raise ValueError(
                    f" areas_dict:{areas} \n"
                    f" len_points: {len(poisson_points)} \n"
                    f" poly: {normalized_polygon}, \n"
                    f" radius: {point_radius}, \n"
                    f" {e}"
                )
            # return gpd.GeoDataFrame()
