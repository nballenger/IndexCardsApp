import pytest

from indexcards.models.document import DEFAULT_CANVAS_BACKGROUND_COLOR
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

    assert migrated["schema_version"] == 2
    assert migrated["file"]["canvas_background_color"] == DEFAULT_CANVAS_BACKGROUND_COLOR
    assert migrated["file"]["name"] == "Old File"


def test_migrate_v1_to_v2_preserves_existing_background_color_if_present():
    data = {
        "schema_version": 1,
        "file": {"name": "Old File", "canvas_background_color": "#123456"},
        "cards": [],
        "links": [],
    }

    migrated = migrate(data)

    assert migrated["file"]["canvas_background_color"] == "#123456"


def test_migrate_v1_to_v2_handles_missing_file_key():
    data = {"schema_version": 1, "cards": [], "links": []}

    migrated = migrate(data)

    assert migrated["file"]["canvas_background_color"] == DEFAULT_CANVAS_BACKGROUND_COLOR


def test_migrate_does_not_mutate_input_dict():
    original = {"schema_version": 1, "file": {"name": "Old File"}, "cards": [], "links": []}
    original_copy = {"schema_version": 1, "file": {"name": "Old File"}, "cards": [], "links": []}

    migrate(original)

    assert original == original_copy
