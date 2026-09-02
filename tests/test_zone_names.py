import pytest

from app.common.constants.api_constants import (
    default_terr_zones_map,
    profile_name_by_id,
    profile_names,
    resolve_profile_id,
    resolve_territory_zone_id,
    scenario_func_zones_map,
    territory_zone_name_by_id,
    territory_zone_names,
)


@pytest.mark.parametrize(
    "value, expected",
    [
        ("жилая", 1),
        ("Жильё", 1),
        ("  жилая зона ", 1),
        ("жилая застройка", 1),
        ("рекреационная", 2),
        ("парк", 2),
        ("специального назначения", 3),
        ("спец", 3),
        ("промышленная", 4),
        ("промзона", 4),
        ("сельское хозяйство", 5),
        ("транспорт", 6),
        ("общественно-деловая", 7),
        ("residential", 1),
    ],
)
def test_zone_names_and_aliases_resolve_to_ids(value, expected):
    assert resolve_territory_zone_id(value) == expected


def test_numeric_ids_still_resolve():
    assert resolve_territory_zone_id(10) == 10
    assert resolve_territory_zone_id("10") == 10


def test_unknown_reference_resolves_to_nothing():
    assert resolve_territory_zone_id("зона мечты") is None
    assert resolve_territory_zone_id(999) is None
    assert resolve_territory_zone_id(True) is None


def test_a_name_resolves_to_the_canonical_id_of_its_kind():
    """Residential has ids 1/10/11/12/13; the shared name may only mean the canonical one."""

    assert resolve_territory_zone_id("жилая") == 1


def test_basic_profile_exists_only_in_the_profile_id_space():
    assert resolve_profile_id("базовая") == 8
    assert resolve_profile_id(8) == 8
    assert resolve_territory_zone_id("базовая") is None
    assert resolve_territory_zone_id(8) is None


def test_every_listed_name_resolves_back_to_a_generatable_zone():
    for name in territory_zone_names():
        assert str(resolve_territory_zone_id(name)) in default_terr_zones_map
    for name in profile_names():
        assert resolve_profile_id(name) in scenario_func_zones_map


def test_ids_render_back_as_names():
    assert territory_zone_name_by_id(1) == "жилая"
    assert territory_zone_name_by_id(13) == "жилая"
    assert territory_zone_name_by_id(999) is None
    assert profile_name_by_id(8) == "базовая"
