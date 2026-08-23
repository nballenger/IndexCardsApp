import pytest

from indexcards.arrange.auto_arrange import (
    CASCADE_OFFSET,
    STACK_SPACING_X,
    TILE_GUTTER,
    arrange_by_color,
    arrange_by_tag,
    arrange_by_tile,
    auto_arrange_positions,
)
from indexcards.models.card import DEFAULT_CARD_SIZE, Card


def _cards():
    return [
        Card(id="c_1", color="#AAAAAA", tags=["plot"]),
        Card(id="c_2", color="#AAAAAA", tags=[]),
        Card(id="c_3", color="#BBBBBB", tags=["plot", "urgent"]),
        Card(id="c_4", color="#CCCCCC", tags=[]),
    ]


def test_arrange_by_color_exact_layout():
    positions = arrange_by_color(_cards())

    assert positions == {
        "c_1": (0.0, 0.0),
        "c_2": (CASCADE_OFFSET, CASCADE_OFFSET),
        "c_3": (STACK_SPACING_X, 0.0),
        "c_4": (2 * STACK_SPACING_X, 0.0),
    }


def test_arrange_by_color_same_stack_cards_cascade_not_overlap():
    positions = arrange_by_color(_cards())
    # c_1 and c_2 share a color/stack; the diagonal cascade keeps them from
    # landing on the exact same point (which would hide one behind the other).
    assert positions["c_1"] != positions["c_2"]
    # But they stay much closer together than cards in a different stack.
    same_stack_gap = positions["c_2"][0] - positions["c_1"][0]
    different_stack_gap = positions["c_3"][0] - positions["c_1"][0]
    assert same_stack_gap < different_stack_gap


def test_arrange_by_color_covers_every_card():
    cards = _cards()
    positions = arrange_by_color(cards)
    assert set(positions) == {card.id for card in cards}


def test_arrange_by_color_is_deterministic():
    cards = _cards()
    assert arrange_by_color(cards) == arrange_by_color(cards)


def test_arrange_by_tag_exact_layout():
    positions = arrange_by_tag(_cards(), "plot")

    # c_1 and c_3 have "plot" (stack 0); c_2 and c_4 don't (stack 1).
    assert positions == {
        "c_1": (0.0, 0.0),
        "c_3": (CASCADE_OFFSET, CASCADE_OFFSET),
        "c_2": (STACK_SPACING_X, 0.0),
        "c_4": (STACK_SPACING_X + CASCADE_OFFSET, CASCADE_OFFSET),
    }


def test_arrange_by_tag_with_no_matching_cards_still_covers_everyone():
    cards = _cards()
    positions = arrange_by_tag(cards, "nonexistent-tag")
    assert set(positions) == {card.id for card in cards}


def test_auto_arrange_positions_dispatches_color():
    cards = _cards()
    assert auto_arrange_positions(cards, "color") == arrange_by_color(cards)


def test_auto_arrange_positions_dispatches_tag():
    cards = _cards()
    assert auto_arrange_positions(cards, "tag", "plot") == arrange_by_tag(cards, "plot")


def test_auto_arrange_positions_tag_without_tag_value_raises():
    with pytest.raises(ValueError):
        auto_arrange_positions(_cards(), "tag", None)


def test_auto_arrange_positions_unknown_mode_raises():
    with pytest.raises(ValueError):
        auto_arrange_positions(_cards(), "nonsense")


def test_arrange_by_tile_covers_every_card():
    cards = _cards()
    positions = arrange_by_tile(cards, aspect_ratio=1.0)
    assert set(positions) == {card.id for card in cards}


def test_arrange_by_tile_empty_list_returns_empty():
    assert arrange_by_tile([], aspect_ratio=1.0) == {}


def test_arrange_by_tile_square_layout_for_square_aspect_ratio():
    cards = [Card(id=f"c_{i}") for i in range(9)]
    positions = arrange_by_tile(cards, aspect_ratio=1.0)

    columns = {x for x, _y in positions.values()}
    rows = {y for _x, y in positions.values()}
    assert len(columns) == 3
    assert len(rows) == 3


def test_arrange_by_tile_wide_aspect_ratio_yields_more_columns_than_rows():
    cards = [Card(id=f"c_{i}") for i in range(8)]
    positions = arrange_by_tile(cards, aspect_ratio=4.0)

    columns = {x for x, _y in positions.values()}
    rows = {y for _x, y in positions.values()}
    assert len(columns) > len(rows)


def test_arrange_by_tile_no_two_cards_share_a_position():
    cards = [Card(id=f"c_{i}") for i in range(12)]
    positions = arrange_by_tile(cards, aspect_ratio=1.5)
    assert len(set(positions.values())) == len(cards)


def test_arrange_by_tile_uses_card_size_plus_gutter_spacing():
    cards = [Card(id="c_1"), Card(id="c_2")]
    positions = arrange_by_tile(cards, aspect_ratio=4.0)  # forces a single row

    width, _height = DEFAULT_CARD_SIZE
    assert positions["c_1"] == (0.0, 0.0)
    assert positions["c_2"] == (width + TILE_GUTTER, 0.0)


def test_arrange_by_tile_is_deterministic():
    cards = _cards()
    assert arrange_by_tile(cards, aspect_ratio=1.3) == arrange_by_tile(cards, aspect_ratio=1.3)


def test_auto_arrange_positions_dispatches_tile():
    cards = _cards()
    assert auto_arrange_positions(cards, "tile", aspect_ratio=1.3) == arrange_by_tile(
        cards, aspect_ratio=1.3
    )
