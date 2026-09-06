import pytest

from indexcards.models.theme import Slot, Theme
from indexcards.utils.contrast import (
    auto_text_color,
    best_contrasting_color,
    contrast_ratio,
    relative_luminance,
    selection_outline_color,
)


def test_relative_luminance_of_white_is_one():
    assert relative_luminance("#ffffff") == pytest.approx(1.0)


def test_relative_luminance_of_black_is_zero():
    assert relative_luminance("#000000") == pytest.approx(0.0)


def test_contrast_ratio_of_black_and_white_is_21():
    assert contrast_ratio("#ffffff", "#000000") == pytest.approx(21.0, rel=1e-3)


def test_contrast_ratio_is_symmetric():
    assert contrast_ratio("#336699", "#ffffff") == pytest.approx(
        contrast_ratio("#ffffff", "#336699")
    )


def test_contrast_ratio_of_a_color_with_itself_is_one():
    assert contrast_ratio("#336699", "#336699") == pytest.approx(1.0)


def test_auto_text_color_picks_black_on_light_background():
    assert auto_text_color("#f6e27a") == "#000000"  # today's Yellow


def test_auto_text_color_picks_white_on_dark_background():
    assert auto_text_color("#1a1a1a") == "#ffffff"


def test_auto_text_color_on_white_is_black():
    assert auto_text_color("#ffffff") == "#000000"


def test_auto_text_color_on_black_is_white():
    assert auto_text_color("#000000") == "#ffffff"


def test_best_contrasting_color_picks_the_better_worst_case():
    # Two light references: black clearly wins against both, so its
    # worst-case beats white's regardless of which reference is binding.
    assert best_contrasting_color(["#000000", "#ffffff"], ["#f6e27a", "#eeeeee"]) == "#000000"
    # Two dark references: white wins symmetrically.
    assert best_contrasting_color(["#000000", "#ffffff"], ["#1a1a1a", "#111111"]) == "#ffffff"


def test_best_contrasting_color_worst_case_is_the_binding_constraint():
    # One light, one dark reference: black reads fine against the light
    # one but poorly against the dark one (and vice versa for white) --
    # the *worse* of each candidate's two ratios must decide the outcome,
    # not just one of them. #1a1a1a is close enough to black that black's
    # worst-case (against #1a1a1a) is far below white's worst-case
    # (against #f6e27a), so white must win here.
    assert best_contrasting_color(["#000000", "#ffffff"], ["#f6e27a", "#1a1a1a"]) == "#ffffff"


def test_best_contrasting_color_with_one_reference_matches_auto_text_color():
    assert best_contrasting_color(["#000000", "#ffffff"], ["#f6e27a"]) == auto_text_color(
        "#f6e27a"
    )


def _theme(background_color: str, slot_hexes: list[str]) -> Theme:
    slots = [
        Slot(id=f"slot_{i}", label="", hex=hex_value) for i, hex_value in enumerate(slot_hexes)
    ]
    return Theme(
        id="theme_test",
        name="Test",
        origin="custom",
        background_color=background_color,
        slots=slots,
    )


def test_selection_outline_color_is_white_on_a_dark_theme():
    theme = _theme("#1a1a1a", ["#2a2a2a", "#333333"])
    assert selection_outline_color(theme) == "#ffffff"


def test_selection_outline_color_is_black_on_a_light_theme():
    theme = _theme("#f0f0f0", ["#ffffff", "#f6e27a"])
    assert selection_outline_color(theme) == "#000000"


def test_selection_outline_color_ignores_orphaned_slots():
    # An orphaned slot renders hatched, not as a flat fill -- it isn't a
    # real contrast reference. Verified by construction to actually matter
    # here: a dark background + dark active slot both call for white, but
    # a light orphaned slot would (if wrongly included) drag white's own
    # worst-case down and flip the choice to black.
    theme = Theme(
        id="theme_test",
        name="Test",
        origin="custom",
        background_color="#1a1a1a",
        slots=[
            Slot(id="slot_active", label="", hex="#2a2a2a"),
            Slot(id="slot_orphan", label="", hex="#ffffff", orphaned=True),
        ],
    )
    assert selection_outline_color(theme) == "#ffffff"
