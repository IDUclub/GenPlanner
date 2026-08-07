from genplanner import basic_func_zone, TerritoryZone
from genplanner import default_func_zones as func_zones
from genplanner import default_terr_zones as terr_zones
from genplanner.zones import TerritoryZoneKind

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


custom_ter_zones_map_by_name = {
    "residential": terr_zones.residential_terr,
    "industrial": terr_zones.industrial_terr,
    "business": terr_zones.business_terr,
    "recreation": terr_zones.recreation_terr,
    "transport": terr_zones.transport_terr,
    "agriculture": terr_zones.agriculture_terr,
    "special": terr_zones.special_terr,
}

default_terr_zones_map = {
    "1": TerritoryZone(
        kind=TerritoryZoneKind.RESIDENTIAL, name="1", min_block_area=terr_zones.residential_terr.min_block_area
    ),
    "4": TerritoryZone(
        kind=TerritoryZoneKind.INDUSTRIAL, name="4", min_block_area=terr_zones.industrial_terr.min_block_area
    ),
    "7": TerritoryZone(
        kind=TerritoryZoneKind.BUSINESS, name="7", min_block_area=terr_zones.business_terr.min_block_area
    ),
    "2": TerritoryZone(
        kind=TerritoryZoneKind.RECREATION, name="2", min_block_area=terr_zones.recreation_terr.min_block_area
    ),
    "6": TerritoryZone(
        kind=TerritoryZoneKind.TRANSPORT, name="6", min_block_area=terr_zones.transport_terr.min_block_area
    ),
    "5": TerritoryZone(
        kind=TerritoryZoneKind.AGRICULTURE, name="5", min_block_area=terr_zones.agriculture_terr.min_block_area
    ),
    "3": TerritoryZone(kind=TerritoryZoneKind.SPECIAL, name="3", min_block_area=terr_zones.special_terr.min_block_area),
    "10": TerritoryZone(
        kind=TerritoryZoneKind.RESIDENTIAL, name="10", min_block_area=terr_zones.residential_terr.min_block_area
    ),
    "11": TerritoryZone(
        kind=TerritoryZoneKind.RESIDENTIAL, name="11", min_block_area=terr_zones.residential_terr.min_block_area
    ),
    "12": TerritoryZone(
        kind=TerritoryZoneKind.RESIDENTIAL, name="12", min_block_area=terr_zones.residential_terr.min_block_area
    ),
    "13": TerritoryZone(
        kind=TerritoryZoneKind.RESIDENTIAL, name="13", min_block_area=terr_zones.residential_terr.min_block_area
    ),
}

territory_zone_kind_names_ru: dict[TerritoryZoneKind, str] = {
    TerritoryZoneKind.RESIDENTIAL: "жилая",
    TerritoryZoneKind.INDUSTRIAL: "промышленная",
    TerritoryZoneKind.BUSINESS: "деловая",
    TerritoryZoneKind.RECREATION: "рекреационная",
    TerritoryZoneKind.TRANSPORT: "транспортная",
    TerritoryZoneKind.AGRICULTURE: "сельскохозяйственная",
    TerritoryZoneKind.SPECIAL: "специального назначения",
}

_UNTYPED_ZONE_NAME_RU = "базовая"


def build_zones_reference() -> list[dict[str, str | int | None]]:
    """Describe every generatable zone id with its kind and a human-readable name.

    Callers that only receive ids cannot tell which zone means "жильё": an LLM asked to
    map words to ids either refuses or guesses. Everything here is derived from the zone
    maps themselves, so the reference cannot drift from what generation actually uses.
    """
    reference: list[dict[str, str | int | None]] = []
    for zone_id in sorted(scenario_func_zones_map):
        territory_zone = default_terr_zones_map.get(str(zone_id))
        kind = territory_zone.kind if territory_zone else None
        reference.append(
            {
                "id": zone_id,
                "kind": kind.value if kind else None,
                "name": territory_zone_kind_names_ru[kind] if kind else _UNTYPED_ZONE_NAME_RU,
                "profile": getattr(scenario_func_zones_map[zone_id], "name", None),
            }
        )
    return reference
