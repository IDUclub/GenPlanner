from app.chat.agent.draft import GenerationDraft


def test_merge_patch_resolves_zone_names_to_ids():
    merged = GenerationDraft().merge_patch({"territory_balance": {"жилая": 0.6, "рекреационная": 0.4}})

    assert merged.territory_balance == {1: 0.6, 2: 0.4}


def test_merge_patch_still_accepts_numeric_ids():
    merged = GenerationDraft().merge_patch({"territory_balance": {"1": 0.5, "10": 0.5}})

    assert merged.territory_balance == {1: 0.5, 10: 0.5}


def test_merge_patch_resolves_pairs_by_name():
    merged = GenerationDraft().merge_patch(
        {
            "territory_balance": {"жилая": 1.0},
            "neighbour_pairs": [["жилая", "рекреационная"]],
            "forbidden_pairs": [["жилая", "промышленная"]],
        }
    )

    assert merged.neighbour_pairs == [(1, 2)]
    assert merged.forbidden_pairs == [(1, 4)]


def test_min_block_area_is_keyed_by_zone_name_too():
    merged = GenerationDraft().merge_patch({"min_block_area": {"деловая": 5000}})

    assert merged.min_block_area == {7: 5000.0}


def test_unknown_zone_is_dropped_from_the_balance():
    merged = GenerationDraft().merge_patch({"territory_balance": {"жилая": 0.5, "зона мечты": 0.5}})

    assert merged.territory_balance == {1: 0.5}


def test_a_fully_unresolvable_patch_leaves_the_previous_balance_intact():
    draft = GenerationDraft(territory_balance={1: 1.0})
    merged = draft.merge_patch({"territory_balance": {"зона мечты": 1.0}})

    assert merged.territory_balance == {1: 1.0}


def test_half_resolvable_pair_is_dropped_whole():
    merged = GenerationDraft().merge_patch({"forbidden_pairs": [["жилая", "зона мечты"]]})

    assert merged.forbidden_pairs is None


def test_non_zone_fields_are_untouched():
    merged = GenerationDraft().merge_patch({"elevation_angle": 15, "roads_extend_distance": 5.0})

    assert merged.elevation_angle == 15
    assert merged.roads_extend_distance == 5.0


def test_named_view_renders_ids_back_as_names():
    draft = GenerationDraft(territory_balance={1: 0.5, 2: 0.5}, forbidden_pairs=[(1, 4)], elevation_angle=10)

    assert draft.as_named_dict() == {
        "territory_balance": {"жилая": 0.5, "рекреационная": 0.5},
        "forbidden_pairs": [["жилая", "промышленная"]],
        "elevation_angle": 10,
    }
