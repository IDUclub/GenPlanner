import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import CRS
from rust_optimizer import optimize_space
from shapely import Point
from shapely.geometry import LineString, MultiPolygon, Polygon

from app.gen_planner.python.src._config import config
from app.gen_planner.python.src.utils import (
    denormalize_coords,
    generate_points,
    normalize_coords,
    polygon_angle,
    rotate_coords,
)

poisson_n_radius = config.poisson_n_radius.copy()
roads_width_def = config.roads_width_def.copy()


def gdf_splitter(task, **kwargs):
    gdf, areas_dict, roads_width, fixed_zones = task
    n_areas = len(areas_dict)
    generated_zones = []
    generated_roads = []
    local_crs = gdf.crs
    for ind, row in gdf.iterrows():
        polygon = row.geometry
        pivot_point = polygon.centroid
        angle_rad_to_rotate = polygon_angle(polygon)
        if len(fixed_zones) > 0:
            fixed_zones_in_poly = fixed_zones[fixed_zones.within(polygon)]
            if len(fixed_zones_in_poly) > 0:
                fixed_zones_in_poly["geometry"] = fixed_zones_in_poly["geometry"].apply(
                    lambda x: Point(rotate_coords(x.coords, pivot_point, -angle_rad_to_rotate))
                )
                fixed_zones_in_poly = fixed_zones_in_poly.groupby("fixed_zone").agg({"geometry": list})
                fixed_zones_in_poly = fixed_zones_in_poly["geometry"].to_dict()
            else:
                fixed_zones_in_poly = None
        else:
            fixed_zones_in_poly = None
        polygon = Polygon(rotate_coords(polygon.exterior.coords, pivot_point, -angle_rad_to_rotate))
        zones, roads = _split_polygon(
            polygon=polygon,
            areas_dict=areas_dict,
            point_radius=poisson_n_radius.get(n_areas, 0.1),
            local_crs=local_crs,
            fixed_zone_points=fixed_zones_in_poly,
            dev=kwargs.get("dev_mod"),
        )

        if not zones.empty:
            zones.geometry = zones.geometry.apply(
                lambda x: Polygon(rotate_coords(x.exterior.coords, pivot_point, angle_rad_to_rotate))
            )
        if not roads.empty:
            roads.geometry = roads.geometry.apply(
                lambda x: LineString(rotate_coords(x.coords, pivot_point, angle_rad_to_rotate))
            )
        generated_zones.append(zones)
        generated_roads.append(roads)

    roads = pd.concat(generated_roads, ignore_index=True)
    zones = pd.concat(generated_zones, ignore_index=True)

    roads["road_lvl"] = "undefined"  # TODO kwargs??
    roads["roads_width"] = roads_width if roads_width is not None else roads_width_def.get("local road")
    return {"generation": zones, "generated_roads": roads}


def _split_polygon(
    polygon: Polygon,
    areas_dict: dict,
    local_crs: CRS,
    point_radius: float = 0.1,
    zone_connections: list = None,
    fixed_zone_points: dict = None,  # "zone_name(key_from areas_dict): [Point(x,y)]"
    dev=False,
) -> (gpd.GeoDataFrame, gpd.GeoDataFrame):

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

    if zone_connections is None:
        zone_connections = []
    if fixed_zone_points is None:
        fixed_zone_points = {}
    areas_init = pd.DataFrame(list(areas_dict.items()), columns=["zone_name", "ratio"])

    fixed_points = []
    zone_name_to_idx = {zone_name: idx for idx, zone_name in enumerate(areas_init["zone_name"])}

    bounds = polygon.bounds

    for zone_name, points in fixed_zone_points.items():
        if zone_name not in zone_name_to_idx:
            continue
        room_idx = zone_name_to_idx[zone_name]
        for pt in points:
            xy = normalize_coords(pt.coords, bounds)
            fixed_points.append((xy[0][0], xy[0][1], room_idx))
    normalized_polygon = Polygon(normalize_coords(polygon.exterior.coords, bounds))

    attempts = 20
    best_generation = (gpd.GeoDataFrame(), gpd.GeoDataFrame())
    best_multipolygon_count = float("inf")
    best_error = float("inf")
    for i in range(attempts):
        try:
            poisson_points = generate_points(normalized_polygon, point_radius)

            full_area = normalized_polygon.area
            areas = areas_init.copy()

            areas["ratio"] = areas["ratio"] / (areas["ratio"].sum())
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

            site2xy = poisson_points.flatten().round(8).tolist()
            site2xy2flag = [0.0 for _ in range(len(site2room) * 2)]
            site2room = site2room.tolist()

            for x, y, room_idx in fixed_points:
                site2xy.extend([round(x, 8), round(y, 8)])
                site2xy2flag.extend([1.0, 1.0])  # флаг фиксации
                site2room.append(room_idx)

            res = optimize_space(
                vtxl2xy=normalized_border,
                site2xy=site2xy,
                site2room=site2room,
                site2xy2flag=site2xy2flag,
                room2area_trg=areas["area"].sort_index().round(8).tolist(),
                room_connections=zone_connections,
                dev=dev,
            )

            site2idx = res[0]  # number of points [0,5,10,15,20] means there are 4 polygons with indexes 0..5 etc
            idx2vtxv = res[1]  # node indexes for each voronoi poly
            vtxv2xy = res[2]  # all points from generation (+bounds)
            edge2vtxv_wall = res[3]  # complete walls/roads

            vtxv2xy = denormalize_coords(
                [coords for coords in np.array(vtxv2xy).reshape(int(len(vtxv2xy) / 2), 2)], bounds
            )

            polygons, poly_sites = create_polygons(site2idx, site2room, idx2vtxv, np.array(vtxv2xy).flatten().tolist())
            devided_zones = gpd.GeoDataFrame(
                geometry=polygons, data=poly_sites, columns=["zone_id"], crs=local_crs
            ).dissolve("zone_id", as_index=False)

            if len(devided_zones) != len(areas):
                raise ValueError(f"Number of devided_zones does not match {len(areas)}: {len(devided_zones)}")

            devided_zones = devided_zones.merge(areas.reset_index(), left_on="zone_id", right_on="index")

            multipolygon_count = sum(isinstance(geom, MultiPolygon) for geom in devided_zones.geometry)

            # Если кол-во мультиполи больше 0, перезапускаем генерацию, но сохраняем лучший результат
            if multipolygon_count > 0:
                actual_areas = devided_zones.geometry.area
                target_areas = devided_zones["area"]
                area_error = np.mean(np.abs(actual_areas - target_areas))
                if multipolygon_count < best_multipolygon_count or (
                    multipolygon_count == best_multipolygon_count and area_error < best_error
                ):
                    new_roads = [
                        (vtxv2xy[x[0]], vtxv2xy[x[1]])
                        for x in np.array(edge2vtxv_wall).reshape(int(len(edge2vtxv_wall) / 2), 2)
                    ]
                    new_roads = gpd.GeoDataFrame(geometry=[LineString(x) for x in new_roads], crs=local_crs)
                    devided_zones = devided_zones.drop(
                        columns=["zone_id", "index", "ratio", "area", "ratio_sqrt", "area_sqrt", "site_indeed"]
                    )
                    best_generation = (devided_zones.copy(), new_roads.copy())
                    best_multipolygon_count = multipolygon_count
                    best_error = area_error
                raise ValueError(f"MultiPolygon returned from optimizer. Have to recalculate.")

            devided_zones = devided_zones.drop(
                columns=["zone_id", "index", "ratio", "area", "ratio_sqrt", "area_sqrt", "site_indeed"]
            )
            new_roads = [
                (vtxv2xy[x[0]], vtxv2xy[x[1]])
                for x in np.array(edge2vtxv_wall).reshape(int(len(edge2vtxv_wall) / 2), 2)
            ]
            new_roads = gpd.GeoDataFrame(geometry=[LineString(x) for x in new_roads], crs=local_crs)
            return devided_zones, new_roads

        except Exception as e:
            if i + 1 == attempts:
                devided_zones, new_roads = best_generation
                if len(devided_zones) > 0:
                    devided_zones = devided_zones.explode(ignore_index=True)
                else:
                    devided_zones = gpd.GeoDataFrame(geometry=[polygon], crs=local_crs)
                    devided_zones['zone_name'] = ''
                return devided_zones, new_roads
