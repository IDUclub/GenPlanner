from app.gen_planner.python.src.zoning import func_zones, terr_zones, basic_func_zone


scenario_func_zones_map = {
    "Профиль: Базовый": basic_func_zone,
    "Профиль: Жилая зона": func_zones.residential_func_zone,
    "Профиль: Промышленная зона": func_zones.industrial_func_zone,
    "Профиль: Общественно-деловая зона": func_zones.business_func_zone,
    "Профиль: Рекреационная зона": func_zones.recreation_func_zone,
    "Профиль: Транспортная зона": func_zones.transport_func_zone,
    "Профиль: Сельскохозяйственная зона": func_zones.agricalture_func_zone,
    "Профиль: Особого назначения": func_zones.special_func_zone
}

scenario_ter_zones_map = {
    "Профиль: Жилая зона": terr_zones.residential_terr,
    "Профиль: Промышленная зона": terr_zones.industrial_terr,
    "Профиль: Общественно-деловая зона": terr_zones.business_terr,
    "Профиль: Рекреационная зона": terr_zones.recreation_terr,
    "Профиль: Транспортная зона": terr_zones.transport_terr,
    "Профиль: Сельскохозяйственная зона": terr_zones.agriculture_terr,
    "Профиль: Особого назначения": terr_zones.special_terr
}
