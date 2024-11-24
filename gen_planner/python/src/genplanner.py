import geopandas as gpd
import numpy as np
import pandas as pd
from geopandas import GeoDataFrame
from pyproj import CRS
from rust_optimizer import optimize_space
from shapely.geometry import Point, Polygon, MultiPolygon, LineString
from shapely.ops import polygonize, unary_union

from gen_planner.python.src.geom_utils import rotate_coords, polygon_angle, normalize_coords, denormalize_coords, \
    generate_points


class GenPlanner:
    original_territory: Polygon
    local_crs: CRS
    angle_rad_to_rotate: float
    pivot_point: Point

    def __init__(self, territory: gpd.GeoDataFrame, rotation: bool | float = True):
        self.original_territory = self._gdf_to_poly(territory.copy())

        if rotation:
            coord = self.original_territory.exterior.coords
            self.pivot_point = self.original_territory.centroid
            if isinstance(rotation, float):
                self.angle_rad_to_rotate = np.deg2rad(rotation)
                self.original_territory = Polygon(
                    rotate_coords(coord, self.pivot_point, self.angle_rad_to_rotate))
            else:
                self.angle_rad_to_rotate = polygon_angle(self.original_territory)
                self.original_territory = Polygon(
                    rotate_coords(coord, self.pivot_point, -self.angle_rad_to_rotate))

    def _gdf_to_poly(self, gdf: GeoDataFrame) -> Polygon:
        self.local_crs = gdf.estimate_utm_crs()
        poly = gdf.to_crs(self.local_crs).union_all()
        if isinstance(poly, Polygon):
            return poly
        elif isinstance(poly, MultiPolygon):
            # TODO deal with multipolygon
            raise RuntimeError

    def terr2zone2block(self,scenario):
        pass

    def terr2district2zone2block(self,district_areas:list,district_scenarios:list):
        pass

    def run(self):
        # first iteration


        pass


def _generate_blocks(polygon: Polygon, local_crs, areas_dict: dict, point_radius: float = 0.1,
                     zone_connections=None) -> GeoDataFrame:
    if zone_connections is None:
        zone_connections = []
    bounds = polygon.bounds
    normalized_polygon = Polygon(normalize_coords(polygon.exterior.coords, bounds)).buffer(0.02)
    poisson_points = generate_points(normalized_polygon, point_radius)
    full_area = normalized_polygon.area
    areas = pd.DataFrame(list(areas_dict.items()), columns=['zone_name', 'ratio'])
    areas['ratio'] = areas['ratio'] / areas['ratio'].sum()
    areas['area'] = areas['ratio'] * full_area
    areas.sort_values(by='ratio', ascending=True, inplace=True)
    area_per_site = full_area / (len(poisson_points))
    areas['site_indeed'] = round(areas['area'] / area_per_site).astype(int)
    zones = np.random.permutation(np.repeat(areas.index, areas['site_indeed']))
    poisson_points = poisson_points[:len(zones)]
    zones = zones[:len(poisson_points)].astype(int)
    normalized_border = [round(item, 8) for sublist in normalized_polygon.exterior.coords[::-1] for item in sublist]
    res = optimize_space(vtxl2xy=normalized_border,
                         site2xy=poisson_points.flatten().round(8).tolist(),
                         site2room=zones.tolist(),
                         site2xy2flag=[0.0 for _ in range(len(zones) * 2)],
                         room2area_trg=areas['area'].sort_index().round(8).tolist(),
                         room_connections=zone_connections,
                         create_gif=False
                         )
    voronoi_points = res[1]
    new_roads_points = res[0]
    voronoi_sites = res[2]

    voronoi_points = [coords for coords in
                      np.array(voronoi_points).reshape(int(len(voronoi_points) / 2), 2)]

    new_roads = [denormalize_coords((voronoi_points[x[0]], voronoi_points[x[1]]), bounds) for x in
                 np.array(new_roads_points).reshape(int(len(new_roads_points) / 2), 2)]
    new_roads = [LineString(x) for x in new_roads]

    roads_w_border = new_roads + [LineString(polygon.exterior.coords)]

    devided_zones = gpd.GeoDataFrame(geometry=list(polygonize((unary_union(roads_w_border)))), crs=local_crs)
    centroids = denormalize_coords(
        [coords for coords in np.array(voronoi_sites).reshape(int(len(voronoi_sites) / 2), 2)], bounds)
    centroids = gpd.GeoDataFrame(data={'zone': zones}, geometry=[Point(x) for x in centroids], crs=local_crs)
    devided_zones = devided_zones.sjoin(centroids, how='left').groupby('zone').agg({'geometry': 'first'}).reset_index()
    devided_zones = devided_zones.merge(areas.reset_index(), left_on='zone', right_on='index').drop(
        columns=['index', 'area', 'site_indeed'])
    return devided_zones