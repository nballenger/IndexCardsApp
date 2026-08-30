import pytest

from indexcards.models.palette import PALETTE
from indexcards.models.presets import PRESET_THEMES, get_preset_theme
from indexcards.utils.contrast import auto_text_color, contrast_ratio

_MIN_AA_CONTRAST = 4.5


def test_exactly_four_presets():
    assert len(PRESET_THEMES) == 4


def test_preset_order_and_names():
    assert [theme.name for theme in PRESET_THEMES] == ["Classic", "Vivid", "Midnight", "Accessible"]


def test_classic_is_first_and_is_the_app_wide_default():
    # Document()/AppSettings.DEFAULT_DEFAULT_THEME_ID both assume this.
    assert PRESET_THEMES[0].id == "preset_classic"


@pytest.mark.parametrize("theme", PRESET_THEMES, ids=lambda t: t.name)
def test_every_preset_is_read_only_origin(theme):
    assert theme.origin == "preset"


@pytest.mark.parametrize("theme", PRESET_THEMES, ids=lambda t: t.name)
def test_every_preset_slot_starts_unorphaned_with_auto_text_color(theme):
    assert all(not slot.orphaned for slot in theme.slots)
    assert all(slot.text_color is None for slot in theme.slots)


@pytest.mark.parametrize("theme", PRESET_THEMES, ids=lambda t: t.name)
def test_every_preset_has_unique_slot_ids(theme):
    ids = [slot.id for slot in theme.slots]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("theme", PRESET_THEMES, ids=lambda t: t.name)
def test_every_preset_has_unique_slot_hexes(theme):
    hexes = [slot.hex.upper() for slot in theme.slots]
    assert len(hexes) == len(set(hexes)), "two slots in the same theme share a color"


@pytest.mark.parametrize("theme", PRESET_THEMES, ids=lambda t: t.name)
def test_every_preset_slot_meets_wcag_aa_text_contrast(theme):
    for slot in theme.slots:
        text = auto_text_color(slot.hex)
        ratio = contrast_ratio(slot.hex, text)
        assert ratio >= _MIN_AA_CONTRAST, f"{theme.name}/{slot.label} only {ratio:.2f}:1"


@pytest.mark.parametrize("theme", PRESET_THEMES, ids=lambda t: t.name)
def test_every_preset_ids_are_deterministic_across_rebuilds(theme):
    # PRESET_THEMES is built once at import time; re-fetching by id must
    # always resolve back to the exact same object (not a fresh rebuild
    # with, say, randomly-generated ids).
    assert get_preset_theme(theme.id) is theme


def test_classic_preset_matches_the_original_flat_palette():
    theme = get_preset_theme("preset_classic")
    assert len(theme.slots) == len(PALETTE)
    assert {slot.hex for slot in theme.slots} == set(PALETTE.values())
    assert [slot.id for slot in theme.slots] == [f"slot_{name.lower()}" for name in PALETTE]


def test_classic_preset_background_color():
    assert get_preset_theme("preset_classic").background_color == "#3d6b4f"


def test_vivid_preset_shape():
    theme = get_preset_theme("preset_vivid")
    assert theme is not None
    assert theme.background_color == "#1F2733"
    assert len(theme.slots) == 7
    assert all(slot.id.startswith("vivid_") for slot in theme.slots)


def test_midnight_preset_shape():
    theme = get_preset_theme("preset_midnight")
    assert theme is not None
    assert theme.background_color == "#121212"
    assert len(theme.slots) == 7
    assert all(slot.id.startswith("midnight_") for slot in theme.slots)


def test_accessible_preset_shape():
    theme = get_preset_theme("preset_accessible")
    assert theme is not None
    assert theme.background_color == "#F4F3EE"
    assert len(theme.slots) == 7
    assert all(slot.id.startswith("accessible_") for slot in theme.slots)


def test_get_preset_theme_returns_none_for_unknown_id():
    assert get_preset_theme("nope") is None
