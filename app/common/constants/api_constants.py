import re

from genplanner import TerritoryZone, basic_func_zone
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


_ZONE_NAME_ALIASES_RU: dict[TerritoryZoneKind, tuple[str, ...]] = {
    TerritoryZoneKind.RESIDENTIAL: ("жилье", "жилищная", "селитебная", "жилая застройка"),
    TerritoryZoneKind.INDUSTRIAL: ("промышленность", "промзона", "производственная"),
    TerritoryZoneKind.BUSINESS: ("общественно-деловая", "общественная", "бизнес"),
    TerritoryZoneKind.RECREATION: ("рекреация", "зеленая", "парковая", "парк"),
    TerritoryZoneKind.TRANSPORT: ("транспорт", "транспортно-логистическая"),
    TerritoryZoneKind.AGRICULTURE: ("сельское хозяйство", "сельхоз", "аграрная", "агро"),
    TerritoryZoneKind.SPECIAL: ("специальная", "спецназначения", "спец"),
}

_BASIC_PROFILE_ID = 8
_BASIC_PROFILE_ALIASES = ("базовый", "универсальная", "basic")

_NAME_NOISE_WORDS = ("зона", "зоны", "зон", "зонирование", "зонирования", "профиль", "профиля", "территория")


def _normalize_zone_name(value: str) -> str:
    """Fold a user/LLM-written zone name to the form the lookup tables are keyed by."""

    text = value.strip().lower().replace("ё", "е")
    text = re.sub(r"[^\w\s-]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _strip_noise_words(name: str) -> str:
    """Drop filler words like "зона"/"профиль" so «жилая зона» resolves like «жилая»."""

    words = [word for word in name.split(" ") if word not in _NAME_NOISE_WORDS]
    return " ".join(words)


def _canonical_id_by_kind() -> dict[TerritoryZoneKind, int]:
    """
    Pick one id per zone kind for name -> id resolution.

    Residential has five ids (1, 10, 11, 12, 13) that share a kind and therefore a name,
    so a name can only ever resolve to the canonical (lowest) one; the subprofiles stay
    reachable by their numeric id.
    """

    canonical: dict[TerritoryZoneKind, int] = {}
    for zone_id_str, zone in default_terr_zones_map.items():
        zone_id = int(zone_id_str)
        if zone.kind not in canonical or zone_id < canonical[zone.kind]:
            canonical[zone.kind] = zone_id
    return canonical


def _build_name_to_id_map() -> dict[str, int]:
    """Map every canonical name, alias and English kind value to a territorial zone id."""

    name_to_id: dict[str, int] = {}
    for kind, zone_id in _canonical_id_by_kind().items():
        names = (territory_zone_kind_names_ru[kind], kind.value, *_ZONE_NAME_ALIASES_RU.get(kind, ()))
        for name in names:
            name_to_id[_normalize_zone_name(name)] = zone_id
    return name_to_id


territory_zone_name_to_id: dict[str, int] = _build_name_to_id_map()

profile_name_to_id: dict[str, int] = {
    **territory_zone_name_to_id,
    **{_normalize_zone_name(name): _BASIC_PROFILE_ID for name in (_UNTYPED_ZONE_NAME_RU, *_BASIC_PROFILE_ALIASES)},
}


def _resolve_zone_reference(value: int | str, name_to_id: dict[str, int], known_ids: set[int]) -> int | None:
    """
    Resolve either a numeric zone id or a human-readable zone name to a zone id.

    Returns None for anything unknown, so callers can drop the reference instead of
    passing an id generation would choke on.
    """

    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value in known_ids else None

    if not isinstance(value, str):
        return None

    raw = value.strip()
    if raw.lstrip("+-").isdigit():
        return int(raw) if int(raw) in known_ids else None

    name = _normalize_zone_name(raw)
    if name in name_to_id:
        return name_to_id[name]
    return name_to_id.get(_strip_noise_words(name))


def resolve_territory_zone_id(value: int | str) -> int | None:
    """Resolve a territorial zone id or name (as used in territory_balance) to its id."""

    known_ids = {int(zone_id) for zone_id in default_terr_zones_map}
    return _resolve_zone_reference(value, territory_zone_name_to_id, known_ids)


def resolve_profile_id(value: int | str) -> int | None:
    """Resolve a zoning profile id or name (as used by custom generation) to its id."""

    return _resolve_zone_reference(value, profile_name_to_id, set(scenario_func_zones_map))


def territory_zone_names() -> list[str]:
    """Canonical territorial zone names, in zone id order — the vocabulary the chat uses."""

    canonical = _canonical_id_by_kind()
    return [territory_zone_kind_names_ru[kind] for kind in sorted(canonical, key=lambda kind: canonical[kind])]


def profile_names() -> list[str]:
    """Canonical zoning profile names, in profile id order."""

    return [*territory_zone_names(), _UNTYPED_ZONE_NAME_RU]


def territory_zone_name_by_id(zone_id: int | str) -> str | None:
    """
    Human-readable name of a territorial zone id, for showing a draft back in zone names.

    Residential subprofile ids (10-13) share the canonical name «жилая»: rendering them by
    name is lossy on purpose -- they behave identically in generation and differ only in
    the id echoed back in the response.
    """

    zone = default_terr_zones_map.get(str(zone_id))
    return territory_zone_kind_names_ru.get(zone.kind) if zone else None


def profile_name_by_id(profile_id: int | str) -> str | None:
    """Human-readable name of a zoning profile id (territorial zones plus the basic profile)."""

    if str(profile_id) == str(_BASIC_PROFILE_ID):
        return _UNTYPED_ZONE_NAME_RU
    return territory_zone_name_by_id(profile_id)
