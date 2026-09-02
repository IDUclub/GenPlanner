from app.chat.agent.custom_draft import CustomGenerationDraft


def test_empty_draft_is_not_ready():
    assert CustomGenerationDraft().is_ready_for_generation() is False


def test_draft_with_profile_id_is_ready():
    assert CustomGenerationDraft(profile_id=1).is_ready_for_generation() is True


def test_merge_patch_sets_unset_field():
    draft = CustomGenerationDraft()
    merged = draft.merge_patch({"profile_id": 7})

    assert merged.profile_id == 7
    assert draft.profile_id is None


def test_merge_patch_overwrites_existing_field():
    draft = CustomGenerationDraft(profile_id=1)
    merged = draft.merge_patch({"profile_id": 2})

    assert merged.profile_id == 2


def test_merge_patch_none_value_leaves_existing_field_untouched():
    draft = CustomGenerationDraft(profile_id=1)
    merged = draft.merge_patch({"profile_id": None})

    assert merged.profile_id == 1


def test_merge_patch_ignores_unknown_keys():
    draft = CustomGenerationDraft()
    merged = draft.merge_patch({"territory_balance": {"1": 0.5}})

    assert merged.profile_id is None


def test_profile_id_out_of_range_is_rejected():
    try:
        CustomGenerationDraft(profile_id=14)
    except Exception as exc:
        assert "profile_id" in str(exc)
    else:
        raise AssertionError("expected validation error for profile_id=14")


def test_merge_patch_accepts_a_profile_name():
    merged = CustomGenerationDraft().merge_patch({"profile": "рекреационная"})

    assert merged.profile_id == 2


def test_merge_patch_accepts_a_profile_alias():
    assert CustomGenerationDraft().merge_patch({"profile": "жильё"}).profile_id == 1


def test_merge_patch_accepts_the_basic_profile_by_name():
    assert CustomGenerationDraft().merge_patch({"profile": "базовая"}).profile_id == 8


def test_merge_patch_keeps_the_previous_profile_when_the_name_is_unknown():
    draft = CustomGenerationDraft(profile_id=2)

    assert draft.merge_patch({"profile": "профиль мечты"}).profile_id == 2


def test_merge_patch_drops_an_id_that_cannot_be_generated():
    assert CustomGenerationDraft().merge_patch({"profile_id": 9}).profile_id is None


def test_named_view_renders_the_profile_id_back_as_a_name():
    assert CustomGenerationDraft(profile_id=1).as_named_dict() == {"profile": "жилая"}
    assert not CustomGenerationDraft().as_named_dict()
