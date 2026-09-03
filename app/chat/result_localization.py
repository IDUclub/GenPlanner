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

from typing import Any

from app.common.constants.api_constants import territory_zone_name_by_id, territory_zone_name_by_kind

ZONE_LABEL_RU = "Территориальная зона"
GENERATED_LABEL_RU = "Сгенерирована"
SOURCE_ZONE_ID_LABEL_RU = "Идентификатор исходной зоны"

ROAD_NAME_LABEL_RU = "Название"
ROAD_ADDRESS_LABEL_RU = "Адрес"

ROAD_LEVEL_KEY = "road_lvl"

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


def _localize_road_properties(properties: dict[str, Any]) -> dict[str, Any]:
    """
    Keep the road attributes a user can read, plus the one the map layer is styled by.

    ``road_lvl`` keeps its machine name and its raw value ("regulated highway",
    "local road, level 2", "user_roads"): the frontend colours the road layer by it, and a
    translated value would make that styling depend on display text.
    """

    localized: dict[str, Any] = {}
    for key, label in (("name", ROAD_NAME_LABEL_RU), ("address", ROAD_ADDRESS_LABEL_RU)):
        value = properties.get(key)
        if value is not None:
            localized[label] = value

    road_level = properties.get(ROAD_LEVEL_KEY)
    if road_level is not None:
        localized[ROAD_LEVEL_KEY] = road_level

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


def localize_result_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the generation result with Russian attribute names and values."""

    return {
        **payload,
        "zones": _localize_feature_collection(payload.get("zones"), _localize_zone_properties),
        "roads": _localize_feature_collection(payload.get("roads"), _localize_road_properties),
    }
