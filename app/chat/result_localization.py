"""
Rewrite a generation result into Russian, human-readable feature attributes.

The chat's ``result`` event feeds a map layer whose attribute panel shows raw GeoJSON
properties straight to the end user, so the technical column names and English zone kinds
the generation pipeline works with (``territory_zone``, ``territory_zone_name``,
``is_generated``) would be read by a planner as untranslated debug output. Everything the
panel shows is renamed and re-valued here, and the numeric zone id is replaced by the zone
name rather than shown alongside it -- ids are an implementation detail the chat never
exposes anywhere else either. The one exception is ``road_lvl``, which survives verbatim
because the layer's styling keys off it.

Only the chat payload goes through this: the REST endpoints keep the machine-readable
schema their existing platform consumers parse.
"""

import re
from functools import partial
from typing import Any

from app.common.constants.api_constants import territory_zone_name_by_id, territory_zone_name_by_kind

ZONE_LABEL_RU = "Территориальная зона"
GENERATED_LABEL_RU = "Сгенерирована"
SOURCE_ZONE_ID_LABEL_RU = "Идентификатор исходной зоны"

ROAD_NAME_LABEL_RU = "Название"
ROAD_ADDRESS_LABEL_RU = "Адрес"

ROAD_LEVEL_KEY = "road_lvl"
ROAD_CLASS_KEY = "road_class"
PHYSICAL_OBJECT_TYPE_KEY = "physical_object_type_id"

ROAD_CLASS_HIGHWAY = "highway"
ROAD_CLASS_STREET = "street"
ROAD_CLASS_EXISTING = "existing"

_ROAD_CLASS_BY_LEVEL_PREFIX: tuple[tuple[str, str], ...] = (
    ("regulated highway", ROAD_CLASS_HIGHWAY),
    ("local road", ROAD_CLASS_STREET),
    ("user_roads", ROAD_CLASS_EXISTING),
)

_UNKNOWN_ZONE_NAME_RU = "не определена"

_YES_RU = "Да"
_NO_RU = "Нет"


def _zone_name(properties: dict[str, Any]) -> str:
    """
    Russian name of the zone a result feature belongs to.

    Both carriers of the zone are tried because neither is guaranteed: generated features
    always have ``territory_zone_name`` (the English kind), while features merged back from
    existing zoning may only carry the numeric ``territory_zone``.
    """

    kind_value = properties.get("territory_zone_name")
    if isinstance(kind_value, str):
        name = territory_zone_name_by_kind(kind_value)
        if name:
            return name

    zone_id = properties.get("territory_zone")
    if zone_id is not None:
        name = territory_zone_name_by_id(zone_id)
        if name:
            return name

    return _UNKNOWN_ZONE_NAME_RU


def _localize_zone_properties(properties: dict[str, Any]) -> dict[str, Any]:
    """
    Build the attribute set shown for one generated zone.

    A whitelist rather than a rename pass: zones merged back from existing functional
    zoning drag along the whole Urban API record (``year``, ``source``, ``created_at``,
    ...), which has no place in a chat result panel and cannot be meaningfully translated
    key by key.
    """

    localized: dict[str, Any] = {ZONE_LABEL_RU: _zone_name(properties)}

    is_generated = properties.get("is_generated")
    if is_generated is not None:
        localized[GENERATED_LABEL_RU] = _YES_RU if is_generated else _NO_RU

    source_zone_id = properties.get("functional_zone_id")
    if source_zone_id is not None:
        localized[SOURCE_ZONE_ID_LABEL_RU] = source_zone_id

    return localized


def _road_class(road_level: Any) -> str | None:
    """
    Fold ``road_lvl`` into one of three values a map legend can be built from.

    The raw field is not a closed set: block-splitting roads are labelled
    "local road, level N" where N runs as deep as a zone's area over its minimum block area
    demands, so a single result carries as many distinct strings as it had splitting depths.
    Unrecognised values yield None rather than a bucket of their own -- an invented category
    would be styled as if it meant something.
    """

    if not isinstance(road_level, str):
        return None

    normalized = re.sub(r"\s+", " ", road_level.strip().lower())
    for prefix, road_class in _ROAD_CLASS_BY_LEVEL_PREFIX:
        if normalized.startswith(prefix):
            return road_class
    return None


def _road_level_without_depth(road_level: Any) -> Any:
    """
    Drop the ``, level N`` suffix the block splitter appends to ``local road``.

    The depth is counted per zone from that zone's area, so the same level means a
    different road in a different zone and nothing can be read from it across a result.
    A level the mapping does not know is returned untouched.
    """

    if not isinstance(road_level, str):
        return road_level

    normalized = re.sub(r"\s+", " ", road_level.strip().lower())
    for prefix, _ in _ROAD_CLASS_BY_LEVEL_PREFIX:
        if normalized.startswith(prefix):
            return prefix
    return road_level


def _localize_road_properties(properties: dict[str, Any], *, trim_level_depth: bool = False) -> dict[str, Any]:
    """
    Keep the road attributes a user can read, plus the ones the map layer is styled by.

    ``physical_object_type_id``, ``road_lvl`` and ``road_class`` keep machine names and
    untranslated values: the frontend colours the road layer by them, and translating what
    styling keys off would tie the layer's colours to display text. Only roads taken from
    the scenario carry a type id -- the ones the generator draws exist nowhere in Urban API,
    and generation from an uploaded border pulls no existing roads at all.
    """

    localized: dict[str, Any] = {}
    for key, label in (("name", ROAD_NAME_LABEL_RU), ("address", ROAD_ADDRESS_LABEL_RU)):
        value = properties.get(key)
        if value is not None:
            localized[label] = value

    object_type_id = properties.get(PHYSICAL_OBJECT_TYPE_KEY)
    if object_type_id is not None:
        localized[PHYSICAL_OBJECT_TYPE_KEY] = object_type_id

    road_level = properties.get(ROAD_LEVEL_KEY)
    if road_level is not None:
        localized[ROAD_LEVEL_KEY] = _road_level_without_depth(road_level) if trim_level_depth else road_level

    road_class = _road_class(road_level)
    if road_class is not None:
        localized[ROAD_CLASS_KEY] = road_class

    return localized


def _localize_feature_collection(collection: Any, localize_properties) -> Any:
    """Apply a property localizer to every feature, leaving geometry untouched."""

    if not isinstance(collection, dict):
        return collection

    features = collection.get("features")
    if not isinstance(features, list):
        return collection

    localized_features = []
    for feature in features:
        if not isinstance(feature, dict):
            localized_features.append(feature)
            continue
        properties = feature.get("properties")
        localized_features.append(
            {**feature, "properties": localize_properties(properties if isinstance(properties, dict) else {})}
        )

    return {**collection, "features": localized_features}


def localize_result_payload(payload: dict[str, Any], *, trim_road_level_depth: bool = False) -> dict[str, Any]:
    """
    Return the generation result with Russian attribute names and values.

    ``trim_road_level_depth`` is passed by the custom-territory chat, where every road is
    generated: without the depth ``road_lvl`` there holds two values instead of one per
    splitting depth.
    """

    return {
        **payload,
        "zones": _localize_feature_collection(payload.get("zones"), _localize_zone_properties),
        "roads": _localize_feature_collection(
            payload.get("roads"), partial(_localize_road_properties, trim_level_depth=trim_road_level_depth)
        ),
    }
