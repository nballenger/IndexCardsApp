from indexcards.models.palette import PALETTE
from indexcards.models.presets import PRESET_THEMES, get_preset_theme


def test_exactly_one_placeholder_preset():
    assert len(PRESET_THEMES) == 1


def test_placeholder_preset_is_read_only_origin():
    assert PRESET_THEMES[0].origin == "preset"


def test_placeholder_preset_has_one_slot_per_palette_entry():
    theme = PRESET_THEMES[0]
    assert len(theme.slots) == len(PALETTE)
    assert {slot.hex for slot in theme.slots} == set(PALETTE.values())


def test_placeholder_preset_slot_ids_are_deterministic():
    theme = PRESET_THEMES[0]
    ids = [slot.id for slot in theme.slots]
    assert ids == [f"slot_{name.lower()}" for name in PALETTE]


def test_placeholder_preset_slots_start_unorphaned_with_auto_text_color():
    theme = PRESET_THEMES[0]
    assert all(not slot.orphaned for slot in theme.slots)
    assert all(slot.text_color is None for slot in theme.slots)


def test_get_preset_theme_by_id():
    theme = get_preset_theme("preset_classic")
    assert theme is not None
    assert theme.name == "Classic"


def test_get_preset_theme_returns_none_for_unknown_id():
    assert get_preset_theme("nope") is None
