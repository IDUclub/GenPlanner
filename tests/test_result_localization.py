from app.chat.result_localization import (
    GENERATED_LABEL_RU,
    ROAD_ADDRESS_LABEL_RU,
    ROAD_LEVEL_KEY,
    ROAD_NAME_LABEL_RU,
    SOURCE_ZONE_ID_LABEL_RU,
    ZONE_LABEL_RU,
    localize_result_payload,
)


def _collection(properties: dict) -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]}, "properties": properties}
        ],
    }


def _localized(zones: dict | None = None, roads: dict | None = None) -> dict:
    payload = {
        "zones": _collection(zones if zones is not None else {}),
        "roads": _collection(roads if roads is not None else {}),
    }
    return localize_result_payload(payload)


def _zone_properties(properties: dict) -> dict:
    return _localized(zones=properties)["zones"]["features"][0]["properties"]


def _road_properties(properties: dict) -> dict:
    return _localized(roads=properties)["roads"]["features"][0]["properties"]


def test_zone_kind_wins_over_the_numeric_id():
    properties = _zone_properties({"territory_zone": 4, "territory_zone_name": "recreation", "is_generated": True})

    assert properties[ZONE_LABEL_RU] == "рекреационная"
    assert properties[GENERATED_LABEL_RU] == "Да"
    assert "territory_zone" not in properties


def test_zone_falls_back_to_the_id_when_the_kind_is_missing():
    assert _zone_properties({"territory_zone": 4})[ZONE_LABEL_RU] == "промышленная"


def test_unresolvable_zone_is_reported_as_undefined():
    assert _zone_properties({"territory_zone": 999})[ZONE_LABEL_RU] == "не определена"


def test_transferred_zone_keeps_its_source_id_and_is_not_marked_generated():
    properties = _zone_properties(
        {"territory_zone": 1, "functional_zone_id": 1619712, "is_generated": False, "year": 2025, "source": "PZZ"}
    )

    assert properties[GENERATED_LABEL_RU] == "Нет"
    assert properties[SOURCE_ZONE_ID_LABEL_RU] == 1619712
    assert "year" not in properties
    assert "source" not in properties


def test_road_level_survives_under_its_machine_name():
    properties = _road_properties({"name": "Малоневский канал", "road_lvl": "local road, level 2"})

    assert properties[ROAD_NAME_LABEL_RU] == "Малоневский канал"
    assert properties[ROAD_LEVEL_KEY] == "local road, level 2"


def test_road_without_a_level_gets_no_level_key():
    properties = _road_properties({"name": "Улица", "address": "Адрес", "roads_width": 5})

    assert properties == {ROAD_NAME_LABEL_RU: "Улица", ROAD_ADDRESS_LABEL_RU: "Адрес"}


def test_generated_road_carries_only_its_level():
    assert _road_properties({"road_lvl": "regulated highway"}) == {ROAD_LEVEL_KEY: "regulated highway"}


def test_geometry_and_collection_shape_are_untouched():
    payload = _localized(roads={"road_lvl": "user_roads"})

    assert payload["roads"]["type"] == "FeatureCollection"
    assert payload["roads"]["features"][0]["geometry"] == {"type": "Point", "coordinates": [0, 0]}
