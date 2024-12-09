import math

import numpy as np
from scipy.stats._qmc import PoissonDisk
from shapely import Point, Polygon


def rotate_coords(coords: list, pivot: Point, angle_rad: float) -> list[tuple[float, float]]:
    px, py = pivot.x, pivot.y
    rotated_coords = []
    for x, y in coords:
        translated_x = x - px
        translated_y = y - py

        rotated_x = translated_x * math.cos(angle_rad) - translated_y * math.sin(angle_rad)
        rotated_y = translated_x * math.sin(angle_rad) + translated_y * math.cos(angle_rad)

        final_x = rotated_x + px
        final_y = rotated_y + py
        rotated_coords.append((final_x, final_y))
    return rotated_coords


def polygon_angle(rect: Polygon) -> float:
    rect = rect.minimum_rotated_rectangle
    coords = list(rect.exterior.coords)[:-1]
    sides = [(coords[0], coords[1]), (coords[1], coords[2])]

    lengths = [
        math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
        for (x1, y1), (x2, y2) in sides
    ]
    long_side_idx = lengths.index(max(lengths))
    long_side = sides[long_side_idx]

    (x1, y1), (x2, y2) = long_side
    angle_rad = math.atan2(y2 - y1, x2 - x1)
    return angle_rad


def normalize_coords(coords: list[tuple[float, float]], bounds: tuple):
    minx, miny, maxx, maxy = bounds
    width = maxx - minx
    height = maxy - miny
    scale = max(width, height)
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    normalized_coords = [
        ((x - cx) / scale + 0.5, (y - cy) / scale + 0.5)
        for x, y in coords
    ]
    return normalized_coords


def denormalize_coords(normalized_coords: list[tuple[float, float]], bounds: tuple):
    minx, miny, maxx, maxy = bounds
    width = maxx - minx
    height = maxy - miny
    scale = max(width, height)
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    denormalized_coords = [
        (
            (x - 0.5) * scale + cx,
            (y - 0.5) * scale + cy
        )
        for x, y in normalized_coords
    ]

    return denormalized_coords

def generate_points(area_to_fill: Polygon, radius, seed=None):
    if seed is None:
        seed = np.random.default_rng()

    bbox = area_to_fill.envelope
    min_x, min_y, max_x, max_y = bbox.bounds

    width = max_x - min_x
    height = max_y - min_y

    norm_radius = radius / max(width, height)

    engine = PoissonDisk(d=2, radius=norm_radius, seed=seed)
    points = engine.random(int(bbox.area // (math.pi * radius ** 2)) * 10)

    points[:, 0] = points[:, 0] * width + min_x
    points[:, 1] = points[:, 1] * height + min_y

    points_in_polygon = np.array([point for point in points])

    return points_in_polygon