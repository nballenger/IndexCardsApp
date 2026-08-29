import pytest

from indexcards.models.document import DEFAULT_CANVAS_BACKGROUND_COLOR
from indexcards.models.palette import PALETTE
from indexcards.persistence.migrations import CURRENT_SCHEMA_VERSION, migrate


def test_migrate_current_version_is_a_no_op():
    data = {"schema_version": CURRENT_SCHEMA_VERSION, "cards": [], "links": []}
    assert migrate(data) == data


def test_migrate_rejects_future_schema_version():
    data = {"schema_version": CURRENT_SCHEMA_VERSION + 1}
    with pytest.raises(ValueError):
        migrate(data)


def test_migrate_v1_to_v2_adds_default_canvas_background_color():
    data = {"schema_version": 1, "file": {"name": "Old File"}, "cards": [], "links": []}

    migrated = migrate(data)

    assert migrated["schema_version"] == CURRENT_SCHEMA_VERSION
    # canvas_background_color moves off `file` and into `theme` at v4->v5
    # (see test_migrate_v4_to_v5_*), so by the time migration reaches the
    # current version it's surfaced there instead.
    assert migrated["theme"]["background_color"] == DEFAULT_CANVAS_BACKGROUND_COLOR
    assert migrated["file"]["name"] == "Old File"


def test_migrate_v2_to_v3_adds_default_pinned_to_every_card():
    data = {
        "schema_version": 2,
        "file": {"name": "Old File", "canvas_background_color": "#123456"},
        "cards": [{"id": "c_1", "text": "hi"}, {"id": "c_2", "text": "there"}],
        "links": [],
    }

    migrated = migrate(data)

    assert migrated["schema_version"] == CURRENT_SCHEMA_VERSION
    assert [card["pinned"] for card in migrated["cards"]] == [False, False]
    assert [card["id"] for card in migrated["cards"]] == ["c_1", "c_2"]


def test_migrate_v2_to_v3_preserves_existing_pinned_value_if_present():
    data = {
        "schema_version": 2,
        "file": {"name": "Old File"},
        "cards": [{"id": "c_1", "text": "hi", "pinned": True}],
        "links": [],
    }

    migrated = migrate(data)

    assert migrated["cards"][0]["pinned"] is True


def test_migrate_v1_to_v2_preserves_existing_background_color_if_present():
    data = {
        "schema_version": 1,
        "file": {"name": "Old File", "canvas_background_color": "#123456"},
        "cards": [],
        "links": [],
    }

    migrated = migrate(data)

    assert migrated["theme"]["background_color"] == "#123456"


def test_migrate_v1_to_v2_handles_missing_file_key():
    data = {"schema_version": 1, "cards": [], "links": []}

    migrated = migrate(data)

    assert migrated["theme"]["background_color"] == DEFAULT_CANVAS_BACKGROUND_COLOR


def test_migrate_v3_to_v4_adds_stacks_array_and_card_stack_id():
    data = {
        "schema_version": 3,
        "file": {"name": "Old File"},
        "cards": [{"id": "c_1", "text": "hi", "pinned": False}],
        "links": [],
    }

    migrated = migrate(data)

    assert migrated["schema_version"] == CURRENT_SCHEMA_VERSION
    assert migrated["stacks"] == []
    assert migrated["cards"][0]["stack_id"] is None


def test_migrate_v3_to_v4_preserves_existing_stacks_if_present():
    data = {
        "schema_version": 3,
        "file": {"name": "Old File"},
        "cards": [{"id": "c_1", "text": "hi", "pinned": False, "stack_id": "s_1"}],
        "links": [],
        "stacks": [{"id": "s_1", "card_ids": ["c_1"]}],
    }

    migrated = migrate(data)

    assert migrated["stacks"] == [{"id": "s_1", "card_ids": ["c_1"]}]
    assert migrated["cards"][0]["stack_id"] == "s_1"


def test_migrate_does_not_mutate_input_dict():
    original = {"schema_version": 1, "file": {"name": "Old File"}, "cards": [], "links": []}
    original_copy = {"schema_version": 1, "file": {"name": "Old File"}, "cards": [], "links": []}

    migrate(original)

    assert original == original_copy


def _v4_card(card_id: str, color: str) -> dict:
    return {"id": card_id, "text": card_id, "color": color, "pinned": False, "stack_id": None}


def test_migrate_v4_to_v5_builds_classic_theme_from_palette():
    data = {
        "schema_version": 4,
        "file": {"name": "Old File", "canvas_background_color": "#112233"},
        "cards": [],
        "links": [],
        "stacks": [],
    }

    migrated = migrate(data)

    assert migrated["schema_version"] == CURRENT_SCHEMA_VERSION
    assert "canvas_background_color" not in migrated["file"]
    assert migrated["theme"]["id"] == "preset_classic"
    assert migrated["theme"]["origin"] == "preset"
    assert migrated["theme"]["background_color"] == "#112233"
    assert len(migrated["theme"]["slots"]) == len(PALETTE)
    assert {slot["hex"] for slot in migrated["theme"]["slots"]} == set(PALETTE.values())
    assert all(not slot["orphaned"] for slot in migrated["theme"]["slots"])


def test_migrate_v4_to_v5_rewrites_palette_color_to_matching_slot_id():
    data = {
        "schema_version": 4,
        "file": {"name": "Old File"},
        "cards": [_v4_card("c_1", PALETTE["Yellow"])],
        "links": [],
        "stacks": [],
    }

    migrated = migrate(data)

    assert "color" not in migrated["cards"][0]
    yellow_slot_id = next(
        slot["id"] for slot in migrated["theme"]["slots"] if slot["hex"] == PALETTE["Yellow"]
    )
    assert migrated["cards"][0]["color_slot"] == yellow_slot_id


def test_migrate_v4_to_v5_fabricates_orphaned_slot_for_off_palette_color():
    data = {
        "schema_version": 4,
        "file": {"name": "Old File"},
        "cards": [_v4_card("c_1", "#123abc")],
        "links": [],
        "stacks": [],
    }

    migrated = migrate(data)

    custom_slots = [slot for slot in migrated["theme"]["slots"] if slot["hex"] == "#123abc"]
    assert len(custom_slots) == 1
    assert custom_slots[0]["orphaned"] is True
    assert migrated["cards"][0]["color_slot"] == custom_slots[0]["id"]


def test_migrate_v4_to_v5_two_cards_sharing_an_off_palette_color_share_one_slot():
    data = {
        "schema_version": 4,
        "file": {"name": "Old File"},
        "cards": [_v4_card("c_1", "#123abc"), _v4_card("c_2", "#123abc")],
        "links": [],
        "stacks": [],
    }

    migrated = migrate(data)

    slot_ids = {card["color_slot"] for card in migrated["cards"]}
    assert len(slot_ids) == 1
    custom_slots = [slot for slot in migrated["theme"]["slots"] if slot["hex"] == "#123abc"]
    assert len(custom_slots) == 1


def test_migrate_v4_to_v5_adds_color_key_visible_default():
    data = {"schema_version": 4, "file": {}, "cards": [], "links": [], "stacks": []}

    migrated = migrate(data)

    assert migrated["color_key_visible"] is False


def test_migrate_v4_to_v5_is_deterministic():
    data = {
        "schema_version": 4,
        "file": {"name": "Old File"},
        "cards": [_v4_card("c_1", "#123abc")],
        "links": [],
        "stacks": [],
    }

    first = migrate({**data, "cards": [dict(card) for card in data["cards"]]})
    second = migrate({**data, "cards": [dict(card) for card in data["cards"]]})

    assert first == second


def test_migrate_v4_to_v5_does_not_mutate_input_dict():
    original = {
        "schema_version": 4,
        "file": {"name": "Old File", "canvas_background_color": "#112233"},
        "cards": [_v4_card("c_1", "#123abc")],
        "links": [],
        "stacks": [],
    }
    original_copy = {
        "schema_version": 4,
        "file": {"name": "Old File", "canvas_background_color": "#112233"},
        "cards": [_v4_card("c_1", "#123abc")],
        "links": [],
        "stacks": [],
    }

    migrate(original)

    assert original == original_copy
