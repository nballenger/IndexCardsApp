import math
import random

import pytest

from indexcards.arrange.auto_arrange import (
    CASCADE_OFFSET,
    COLUMN_CATEGORY_GUTTER,
    COLUMN_GUTTER,
    SCATTER_MAX_OVERLAP_FRACTION,
    STACK_SPACING_X,
    TILE_GUTTER,
    _positions_bbox,
    _scatter_reach,
    _shift_to_clear_overlap,
    arrange_avoiding_pinned,
    arrange_by_color,
    arrange_by_columns_alphabetical,
    arrange_by_columns_color,
    arrange_by_scatter,
    arrange_by_tag,
    arrange_by_tile,
    auto_arrange_positions,
)
from indexcards.models.card import DEFAULT_CARD_SIZE, Card
from indexcards.models.palette import PALETTE


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
    # aspect_ratio=4.0 forces a single row regardless of shuffle order; a
    # fixed seed pins down which of the two cells each card lands in.
    positions = arrange_by_tile(cards, aspect_ratio=4.0, rng=random.Random(0))

    width, _height = DEFAULT_CARD_SIZE
    assert set(positions.values()) == {(0.0, 0.0), (width + TILE_GUTTER, 0.0)}


def test_arrange_by_tile_is_deterministic_for_a_given_rng_seed():
    cards = _cards()
    positions_a = arrange_by_tile(cards, aspect_ratio=1.3, rng=random.Random(42))
    positions_b = arrange_by_tile(cards, aspect_ratio=1.3, rng=random.Random(42))
    assert positions_a == positions_b


def test_arrange_by_tile_randomizes_placement_order():
    cards = [Card(id=f"c_{i}") for i in range(12)]
    positions_a = arrange_by_tile(cards, aspect_ratio=1.3, rng=random.Random(1))
    positions_b = arrange_by_tile(cards, aspect_ratio=1.3, rng=random.Random(2))
    # Same cards, same grid shape, different seeds — vanishingly unlikely
    # to coincidentally produce the same card-to-cell assignment unless
    # placement order isn't actually being shuffled.
    assert positions_a != positions_b


def test_auto_arrange_positions_dispatches_tile():
    cards = _cards()
    # arrange_by_tile now shuffles placement order using its own internal
    # rng when none is given, so this just confirms the dispatch reaches
    # the tile path (covers every card, same grid shape) rather than
    # comparing against a second, independently-shuffled call.
    positions = auto_arrange_positions(cards, "tile", aspect_ratio=1.3)
    assert set(positions) == {card.id for card in cards}


def _pairwise_overlap_fraction(pos_a, pos_b) -> float:
    width, height = DEFAULT_CARD_SIZE
    ax, ay = pos_a
    bx, by = pos_b
    overlap_x = max(0.0, min(ax + width, bx + width) - max(ax, bx))
    overlap_y = max(0.0, min(ay + height, by + height) - max(ay, by))
    return (overlap_x * overlap_y) / (width * height)


def test_arrange_by_scatter_empty_list_returns_empty():
    assert arrange_by_scatter([]) == {}


def test_arrange_by_scatter_covers_every_card():
    cards = [Card(id=f"c_{i}") for i in range(15)]
    positions = arrange_by_scatter(cards, rng=random.Random(1))
    assert set(positions) == {card.id for card in cards}


def test_arrange_by_scatter_first_card_is_at_origin():
    cards = [Card(id=f"c_{i}") for i in range(5)]
    positions = arrange_by_scatter(cards, rng=random.Random(7))
    assert positions["c_0"] == (0.0, 0.0)


def test_arrange_by_scatter_is_deterministic_for_a_given_rng_seed():
    cards = [Card(id=f"c_{i}") for i in range(10)]
    positions_a = arrange_by_scatter(cards, rng=random.Random(42))
    positions_b = arrange_by_scatter(cards, rng=random.Random(42))
    assert positions_a == positions_b


def test_arrange_by_scatter_respects_overlap_cap_with_room_to_spare():
    # Few cards relative to the search radius — there's plenty of open
    # space, so every card should find a compliant spot within budget
    # rather than needing the least-overlap fallback.
    cards = [Card(id=f"c_{i}") for i in range(8)]
    positions = arrange_by_scatter(cards, rng=random.Random(3))

    ids = list(positions)
    for i, id_a in enumerate(ids):
        for id_b in ids[i + 1 :]:
            overlap = _pairwise_overlap_fraction(positions[id_a], positions[id_b])
            assert overlap <= SCATTER_MAX_OVERLAP_FRACTION + 1e-9


def test_arrange_by_scatter_every_card_has_a_close_neighbor():
    # Distance-to-anchor is always sampled within the search ellipse, so
    # this holds structurally regardless of RNG seed or whether the
    # overlap cap could be satisfied.
    cards = [Card(id=f"c_{i}") for i in range(20)]
    aspect_ratio = 1.7
    positions = arrange_by_scatter(cards, aspect_ratio=aspect_ratio, rng=random.Random(99))
    max_dx, max_dy = _scatter_reach(aspect_ratio)

    ids = list(positions)
    for i, id_a in enumerate(ids):
        ax, ay = positions[id_a]
        others = [positions[id_b] for j, id_b in enumerate(ids) if j != i]
        # Nearest neighbor within the ellipse's normalized distance
        # ((dx/max_dx)^2 + (dy/max_dy)^2 <= 1), not a plain circle.
        nearest_normalized = min(
            math.hypot((ax - bx) / max_dx, (ay - by) / max_dy) for bx, by in others
        )
        assert nearest_normalized <= 1.0 + 1e-9


def test_scatter_reach_is_symmetric_for_square_aspect_ratio():
    width, _height = DEFAULT_CARD_SIZE
    max_dx, max_dy = _scatter_reach(1.0)
    assert max_dx == pytest.approx(2 * width)
    assert max_dy == pytest.approx(2 * width)


def test_scatter_reach_widens_for_wide_aspect_ratio():
    max_dx_square, max_dy_square = _scatter_reach(1.0)
    max_dx_wide, max_dy_wide = _scatter_reach(4.0)

    assert max_dx_wide > max_dx_square
    assert max_dy_wide < max_dy_square
    # Area of the search ellipse is preserved — only its shape changes.
    assert max_dx_wide * max_dy_wide == pytest.approx(max_dx_square * max_dy_square)


def test_scatter_reach_narrows_for_tall_aspect_ratio():
    max_dx_square, max_dy_square = _scatter_reach(1.0)
    max_dx_tall, max_dy_tall = _scatter_reach(0.25)

    assert max_dx_tall < max_dx_square
    assert max_dy_tall > max_dy_square


def test_scatter_reach_falls_back_to_square_for_invalid_aspect_ratio():
    assert _scatter_reach(0.0) == _scatter_reach(1.0)
    assert _scatter_reach(-2.0) == _scatter_reach(1.0)


def _bounding_box(positions: dict[str, tuple[float, float]]) -> tuple[float, float]:
    width, height = DEFAULT_CARD_SIZE
    xs = [x for x, _y in positions.values()]
    ys = [y for _x, y in positions.values()]
    return (max(xs) - min(xs) + width, max(ys) - min(ys) + height)


def test_scatter_cluster_tends_wider_with_wide_aspect_ratio():
    # Statistical, not a single-sample fluke: check the average
    # width:height ratio of the resulting cluster across several seeds
    # is noticeably wider for a wide viewport than a tall one.
    cards = [Card(id=f"c_{i}") for i in range(40)]
    wide_ratios = []
    tall_ratios = []
    for seed in range(10):
        wide_box = _bounding_box(
            arrange_by_scatter(cards, aspect_ratio=3.0, rng=random.Random(seed))
        )
        tall_box = _bounding_box(
            arrange_by_scatter(cards, aspect_ratio=1 / 3, rng=random.Random(seed))
        )
        wide_ratios.append(wide_box[0] / wide_box[1])
        tall_ratios.append(tall_box[0] / tall_box[1])

    avg_wide_ratio = sum(wide_ratios) / len(wide_ratios)
    avg_tall_ratio = sum(tall_ratios) / len(tall_ratios)
    assert avg_wide_ratio > avg_tall_ratio


def test_arrange_by_scatter_falls_back_to_least_overlap_when_space_is_tight():
    # Cramming many cards into a tiny attempt budget with a small radius
    # (via a deliberately small SCATTER_MAX_NEIGHBOR_DISTANCE-like squeeze
    # isn't directly configurable, so instead just use enough cards that
    # some are statistically bound to exhaust their 20 attempts) — the
    # point is this must terminate and still place every card, even if
    # some end up over the overlap cap.
    cards = [Card(id=f"c_{i}") for i in range(60)]
    positions = arrange_by_scatter(cards, rng=random.Random(5))
    assert set(positions) == {card.id for card in cards}


def test_auto_arrange_positions_dispatches_scatter():
    cards = _cards()
    # auto_arrange_positions doesn't expose an rng override, so this just
    # confirms it routes to the scatter path (covers every card) rather
    # than comparing against a separate arrange_by_scatter() call.
    positions = auto_arrange_positions(cards, "scatter")
    assert set(positions) == {card.id for card in cards}
    assert positions[cards[0].id] == (0.0, 0.0)


BLUE = PALETTE["Blue"]
GREEN = PALETTE["Green"]
YELLOW = PALETTE["Yellow"]
WHITE = PALETTE["White"]


def test_arrange_by_columns_color_exact_layout_with_overflow():
    # 4 Blue + 2 Green, overflow_limit=2: Blue splits into two columns
    # (column-major — first 2 sorted cards fill column 1, next 2 spill
    # into an overflow column one COLUMN_GUTTER to the right), then Green
    # starts a new category one COLUMN_CATEGORY_GUTTER further right.
    cards = [
        Card(id="blue_b", text="Bravo", color=BLUE),
        Card(id="blue_a", text="Alpha", color=BLUE),
        Card(id="blue_d", text="Delta", color=BLUE),
        Card(id="blue_c", text="Charlie", color=BLUE),
        Card(id="green_b", text="Beta", color=GREEN),
        Card(id="green_a", text="Aleph", color=GREEN),
    ]

    positions = arrange_by_columns_color(cards, overflow_limit=2)

    width, height = DEFAULT_CARD_SIZE
    col0_x = 0.0
    col1_x = col0_x + width + COLUMN_GUTTER
    col2_x = col1_x + width + COLUMN_CATEGORY_GUTTER
    row1_y = height + COLUMN_GUTTER
    assert positions == {
        "blue_a": (col0_x, 0.0),
        "blue_b": (col0_x, row1_y),
        "blue_c": (col1_x, 0.0),
        "blue_d": (col1_x, row1_y),
        "green_a": (col2_x, 0.0),
        "green_b": (col2_x, row1_y),
    }


def test_arrange_by_columns_color_no_limit_keeps_one_column_per_color():
    cards = [Card(id=f"blue_{i}", text=str(i), color=BLUE) for i in range(5)]

    positions = arrange_by_columns_color(cards, overflow_limit=None)

    assert len({x for x, _y in positions.values()}) == 1
    assert len({y for _x, y in positions.values()}) == 5


def test_arrange_by_columns_color_orders_categories_by_palette_order():
    # Palette order is White, Yellow, Blue, Green, ... — deliberately add
    # cards in a different order to prove the layout doesn't just follow
    # input order or hex-sort order.
    cards = [
        Card(id="green_1", color=GREEN),
        Card(id="blue_1", color=BLUE),
        Card(id="yellow_1", color=YELLOW),
        Card(id="white_1", color=WHITE),
    ]

    positions = arrange_by_columns_color(cards, overflow_limit=None)

    ordered_by_x = sorted(positions, key=lambda card_id: positions[card_id][0])
    assert ordered_by_x == ["white_1", "yellow_1", "blue_1", "green_1"]


def test_arrange_by_columns_color_unknown_colors_sort_after_palette_by_hex():
    cards = [
        Card(id="custom_zz", color="#ZZZZZZ"),
        Card(id="custom_aa", color="#AAAAAA"),
        Card(id="blue_1", color=BLUE),
    ]

    positions = arrange_by_columns_color(cards, overflow_limit=None)

    ordered_by_x = sorted(positions, key=lambda card_id: positions[card_id][0])
    assert ordered_by_x == ["blue_1", "custom_aa", "custom_zz"]


def test_arrange_by_columns_color_sorts_within_category_case_sensitive():
    cards = [
        Card(id="c_lower_b", text="bravo", color=BLUE),
        Card(id="c_upper_a", text="Alpha", color=BLUE),
        Card(id="c_lower_a", text="alpha", color=BLUE),
    ]

    positions = arrange_by_columns_color(cards, overflow_limit=None)

    # Case-sensitive ordering: uppercase 'A' sorts before lowercase letters.
    ordered_by_y = sorted(positions, key=lambda card_id: positions[card_id][1])
    assert ordered_by_y == ["c_upper_a", "c_lower_a", "c_lower_b"]


def test_arrange_by_columns_color_covers_every_card():
    cards = _cards()
    positions = arrange_by_columns_color(cards, overflow_limit=None)
    assert set(positions) == {card.id for card in cards}


def test_arrange_by_columns_alphabetical_groups_by_lowercased_first_letter():
    cards = [
        Card(id="a1", text="apple"),
        Card(id="a2", text="Avocado"),
        Card(id="b1", text="banana"),
    ]

    positions = arrange_by_columns_alphabetical(cards, overflow_limit=None)

    assert positions["a1"][0] == positions["a2"][0]
    assert positions["b1"][0] != positions["a1"][0]
    # 'a' sorts before 'b'.
    assert positions["a1"][0] < positions["b1"][0]


def test_arrange_by_columns_alphabetical_blank_text_sorts_last():
    cards = [
        Card(id="blank_1", text=""),
        Card(id="a1", text="apple"),
        Card(id="z1", text="zebra"),
    ]

    positions = arrange_by_columns_alphabetical(cards, overflow_limit=None)

    rightmost_x = max(positions[card_id][0] for card_id in positions)
    assert positions["blank_1"][0] == rightmost_x
    assert positions["a1"][0] < rightmost_x
    assert positions["z1"][0] < rightmost_x


def test_arrange_by_columns_alphabetical_sorts_within_category_case_sensitive():
    # All three start with 'b'/'B' (case insensitive), so they land in the
    # same column-group; case-sensitive text sort within it puts the
    # uppercase-starting word first (ASCII 'B' < 'a' < 'b').
    cards = [
        Card(id="c_bob_lower", text="bob"),
        Card(id="c_bob_upper", text="Bob"),
        Card(id="c_banana", text="banana"),
    ]

    positions = arrange_by_columns_alphabetical(cards, overflow_limit=None)

    assert positions["c_bob_lower"][0] == positions["c_bob_upper"][0] == positions["c_banana"][0]
    ordered_by_y = sorted(positions, key=lambda card_id: positions[card_id][1])
    assert ordered_by_y == ["c_bob_upper", "c_banana", "c_bob_lower"]


def test_arrange_by_columns_alphabetical_covers_every_card():
    cards = _cards()
    positions = arrange_by_columns_alphabetical(cards, overflow_limit=None)
    assert set(positions) == {card.id for card in cards}


def test_auto_arrange_positions_dispatches_columns_color():
    cards = _cards()
    assert auto_arrange_positions(cards, "columns_color") == arrange_by_columns_color(cards, None)


def test_auto_arrange_positions_dispatches_columns_alphabetical():
    cards = _cards()
    assert auto_arrange_positions(
        cards, "columns_alphabetical"
    ) == arrange_by_columns_alphabetical(cards, None)


def test_auto_arrange_positions_dispatches_columns_color_with_overflow_limit():
    cards = [Card(id=f"c_{i}", text=str(i), color=BLUE) for i in range(4)]
    with_limit = auto_arrange_positions(cards, "columns_color", overflow_limit=2)
    without_limit = auto_arrange_positions(cards, "columns_color", overflow_limit=None)
    assert with_limit != without_limit
    assert len({x for x, _y in with_limit.values()}) == 2
    assert len({x for x, _y in without_limit.values()}) == 1


def test_positions_bbox_covers_full_card_footprint():
    width, height = DEFAULT_CARD_SIZE
    bbox = _positions_bbox({"c_1": (0.0, 0.0), "c_2": (100.0, 50.0)})
    assert bbox == (0.0, 0.0, 100.0 + width, 50.0 + height)


def test_shift_to_clear_overlap_returns_zero_when_already_clear():
    moving = (0.0, 0.0, 100.0, 100.0)
    fixed = (500.0, 500.0, 600.0, 600.0)
    assert _shift_to_clear_overlap(moving, fixed, gutter=10.0) == (0.0, 0.0)


def test_shift_to_clear_overlap_picks_smallest_of_four_directions():
    # fixed spans a wide, short band overlapping only the top strip of
    # moving — shifting down (clearing fixed's bottom edge) is a much
    # smaller move than shifting right/left/up would be.
    moving = (0.0, 0.0, 100.0, 100.0)
    fixed = (-1000.0, 0.0, 50.0, 10.0)
    dx, dy = _shift_to_clear_overlap(moving, fixed, gutter=5.0)
    assert (dx, dy) == pytest.approx((0.0, 15.0))  # (10 - 0) + 5 gutter


def test_shift_to_clear_overlap_result_no_longer_overlaps():
    moving = (0.0, 0.0, 100.0, 80.0)
    fixed = (20.0, 20.0, 90.0, 60.0)
    dx, dy = _shift_to_clear_overlap(moving, fixed, gutter=10.0)
    shifted = (moving[0] + dx, moving[1] + dy, moving[2] + dx, moving[3] + dy)
    no_overlap = (
        shifted[2] <= fixed[0]
        or shifted[0] >= fixed[2]
        or shifted[3] <= fixed[1]
        or shifted[1] >= fixed[3]
    )
    assert no_overlap


def test_arrange_avoiding_pinned_covers_every_card_when_none_pinned():
    cards = [Card(id=f"c_{i}") for i in range(4)]
    positions = arrange_avoiding_pinned(cards, "tile", aspect_ratio=1.0)
    assert set(positions) == {card.id for card in cards}


def test_arrange_avoiding_pinned_leaves_pinned_cards_out_of_the_result():
    cards = [Card(id="c_1", x=500.0, y=500.0, pinned=True), Card(id="c_2")]
    positions = arrange_avoiding_pinned(cards, "tile", aspect_ratio=1.0)
    assert set(positions) == {"c_2"}


def test_arrange_avoiding_pinned_returns_empty_when_all_cards_pinned():
    cards = [Card(id="c_1", pinned=True), Card(id="c_2", pinned=True)]
    assert arrange_avoiding_pinned(cards, "tile", aspect_ratio=1.0) == {}


def test_arrange_avoiding_pinned_shifts_new_layout_clear_of_pinned_bbox():
    width, height = DEFAULT_CARD_SIZE
    # Pinned card sits right where an unpinned tile layout would normally
    # start (the origin), forcing a shift.
    cards = [Card(id="c_pinned", x=0.0, y=0.0, pinned=True)] + [
        Card(id=f"c_{i}") for i in range(4)
    ]

    positions = arrange_avoiding_pinned(cards, "tile", aspect_ratio=1.0)

    assert set(positions) == {"c_0", "c_1", "c_2", "c_3"}
    pinned_bbox = (0.0, 0.0, width, height)
    new_bbox = _positions_bbox(positions)
    no_overlap = (
        new_bbox[2] <= pinned_bbox[0]
        or new_bbox[0] >= pinned_bbox[2]
        or new_bbox[3] <= pinned_bbox[1]
        or new_bbox[1] >= pinned_bbox[3]
    )
    assert no_overlap


def test_arrange_avoiding_pinned_does_not_shift_when_no_overlap():
    # Pinned card is far away from where a fresh tile layout would land
    # (tile always starts near the origin) — nothing should be shifted
    # toward it.
    cards = [Card(id="c_pinned", x=10_000.0, y=10_000.0, pinned=True)] + [
        Card(id=f"c_{i}") for i in range(4)
    ]

    positions = arrange_avoiding_pinned(cards, "tile", aspect_ratio=1.0)

    assert all(abs(x) < 5000 and abs(y) < 5000 for x, y in positions.values())
