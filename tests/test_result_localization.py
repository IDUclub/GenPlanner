import pytest

from app.chat.result_localization import (
    GENERATED_LABEL_RU,
    PHYSICAL_OBJECT_TYPE_KEY,
    ROAD_CLASS_EXISTING,
    ROAD_CLASS_HIGHWAY,
    ROAD_CLASS_KEY,
    ROAD_CLASS_STREET,
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


@pytest.mark.parametrize(
    "road_level, expected",
    [
        ("regulated highway", ROAD_CLASS_HIGHWAY),
        ("local road, level 1", ROAD_CLASS_STREET),
        ("local road, level 7", ROAD_CLASS_STREET),
        ("user_roads", ROAD_CLASS_EXISTING),
    ],
)
def test_every_road_level_folds_into_a_closed_set_of_classes(road_level, expected):
    assert _road_properties({"road_lvl": road_level})[ROAD_CLASS_KEY] == expected


def test_existing_road_keeps_its_urban_api_type():
    properties = _road_properties(
        {"name": "Шлиссельбургское шоссе", "physical_object_type_id": 51, "road_lvl": "user_roads"}
    )

    assert properties[PHYSICAL_OBJECT_TYPE_KEY] == 51
    assert properties[ROAD_CLASS_KEY] == ROAD_CLASS_EXISTING


def test_generated_road_has_no_type_id_to_keep():
    assert PHYSICAL_OBJECT_TYPE_KEY not in _road_properties({"road_lvl": "regulated highway"})


def test_unknown_road_level_gets_no_class():
    properties = _road_properties({"road_lvl": "high speed highway"})

    assert properties[ROAD_LEVEL_KEY] == "high speed highway"
    assert ROAD_CLASS_KEY not in properties


def test_road_without_a_level_gets_neither_level_nor_class():
    properties = _road_properties({"name": "Улица", "address": "Адрес", "roads_width": 5})

    assert properties == {ROAD_NAME_LABEL_RU: "Улица", ROAD_ADDRESS_LABEL_RU: "Адрес"}


def test_generated_road_carries_only_its_level_and_class():
    assert _road_properties({"road_lvl": "regulated highway"}) == {
        ROAD_LEVEL_KEY: "regulated highway",
        ROAD_CLASS_KEY: ROAD_CLASS_HIGHWAY,
    }


def test_geometry_and_collection_shape_are_untouched():
    payload = _localized(roads={"road_lvl": "user_roads"})

    assert payload["roads"]["type"] == "FeatureCollection"
    assert payload["roads"]["features"][0]["geometry"] == {"type": "Point", "coordinates": [0, 0]}
