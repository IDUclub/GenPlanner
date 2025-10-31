from .base_open_api_example import base_open_api_example

gen_planner_func_zone_dto_example = base_open_api_example.copy()
gen_planner_func_zone_dto_example["requestBody"]["content"]["application/json"]["example"] = {
    "fix_zones": {
        "type": "FeatureCollection",
        "name": "fixed_points_example",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": [
            {
                "type": "Feature",
                "properties": {"fixed_zone": 6},
                "geometry": {"type": "Point", "coordinates": [31.046, 59.922]},
            },
            {
                "type": "Feature",
                "properties": {"fixed_zone": 2},
                "geometry": {"type": "Point", "coordinates": [31.043, 59.911]},
            },
            {
                "type": "Feature",
                "properties": {"fixed_zone": 3},
                "geometry": {"type": "Point", "coordinates": [30.999, 59.927]},
            },
            {
                "type": "Feature",
                "properties": {"fixed_zone": 7},
                "geometry": {"type": "Point", "coordinates": [30.993, 59.912]},
            },
        ],
    },
    "min_block_area": {"6": 160000, "2": 130000, "7": 100000},
    "functional_zones": {"year": 2025, "source": "User", "fixed_functional_zones_ids": [1619712]},
    "territory_balance": {"6": 0.4, "2": 0.3, "3": 0.1, "7": 0.2},
}
