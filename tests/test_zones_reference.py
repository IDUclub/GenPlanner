from app.common.constants.api_constants import (
    build_zones_reference,
    default_terr_zones_map,
    scenario_func_zones_map,
)


def test_reference_covers_every_generatable_zone():
    reference = build_zones_reference()

    assert {entry["id"] for entry in reference} == set(scenario_func_zones_map)


def test_reference_names_match_the_zone_kinds():
    by_id = {entry["id"]: entry for entry in build_zones_reference()}

    assert by_id[1]["kind"] == "residential"
    assert by_id[1]["name"] == "жилая"
    assert by_id[5]["kind"] == "agriculture"
    assert by_id[5]["name"] == "сельскохозяйственная"
    assert by_id[3]["kind"] == "special"
    assert by_id[3]["name"] == "специального назначения"


def test_zone_without_a_territory_kind_is_labelled_not_invented():
    by_id = {entry["id"]: entry for entry in build_zones_reference()}

    assert by_id[8]["kind"] is None
    assert by_id[8]["name"] == "базовая"


def test_every_entry_carries_a_name():
    assert all(entry["name"] for entry in build_zones_reference())


def test_reference_stays_consistent_with_the_zone_maps():
    for entry in build_zones_reference():
        territory_zone = default_terr_zones_map.get(str(entry["id"]))
        expected_kind = territory_zone.kind.value if territory_zone else None
        assert entry["kind"] == expected_kind
