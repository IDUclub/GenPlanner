from app.gen_planner.python.src.zoning import basic_func_zone, func_zones, terr_zones

scenario_func_zones_map = {
    8: basic_func_zone,
    1: func_zones.residential_func_zone,
    4: func_zones.industrial_func_zone,
    7: func_zones.business_func_zone,
    2: func_zones.recreation_func_zone,
    6: func_zones.transport_func_zone,
    5: func_zones.agricalture_func_zone,
    3: func_zones.special_func_zone,
    10: func_zones.residential_func_zone,
    11: func_zones.residential_func_zone,
    12: func_zones.residential_func_zone,
    13: func_zones.residential_func_zone,
}

scenario_ter_zones_map = {
    1: terr_zones.residential_terr,
    4: terr_zones.industrial_terr,
    7: terr_zones.business_terr,
    2: terr_zones.recreation_terr,
    6: terr_zones.transport_terr,
    5: terr_zones.agriculture_terr,
    3: terr_zones.special_terr,
    10: terr_zones.residential_terr,
    11: terr_zones.residential_terr,
    12: terr_zones.residential_terr,
    13: terr_zones.residential_terr,
}

custom_func_zones_map_by_name = {
    "basic": basic_func_zone,
    "residential territory": func_zones.residential_func_zone,
    "industrial territory": func_zones.industrial_func_zone,
    "business territory": func_zones.business_func_zone,
    "transport territory": func_zones.transport_func_zone,
    "agriculture territory": func_zones.agricalture_func_zone,
    "special territory": func_zones.special_func_zone,
}

custom_ter_zones_map_by_name = {
    "residential": terr_zones.residential_terr,
    "industrial": terr_zones.industrial_terr,
    "business": terr_zones.business_terr,
    "recreation": terr_zones.recreation_terr,
    "transport": terr_zones.transport_terr,
    "agriculture": terr_zones.agriculture_terr,
    "special": terr_zones.special_terr,
}

