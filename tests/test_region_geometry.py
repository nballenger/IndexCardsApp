from indexcards.models.card import DEFAULT_CARD_SIZE, Card
from indexcards.models.region import (
    CARD_CLEARANCE_SIZE,
    LABEL_BAR_HEIGHT,
    MIN_REGION_SIZE,
    PLACEMENT_GUTTER,
    Region,
)
from indexcards.models.stack import Stack
from indexcards.regions.geometry import (
    bounds_for,
    cards_in_any_region,
    contained_card_ids,
    contained_stack_ids,
    has_room_for_card,
    interior_rect,
    intersect,
    margin_strips,
    stacks_in_any_region,
    to_corner_bbox,
    translate_to_separate,
)


def test_contained_card_ids_uses_the_cards_center_point():
    region = Region(id="r_1", x=0.0, y=0.0, width=300.0, height=200.0)
    inside = Card(id="c_in", x=50.0, y=50.0)  # center (150, 110) is inside
    outside = Card(id="c_out", x=1000.0, y=1000.0)

    assert contained_card_ids(region, [inside, outside]) == ["c_in"]


def test_contained_card_ids_excludes_stacked_cards():
    region = Region(id="r_1", x=0.0, y=0.0, width=300.0, height=200.0)
    stacked = Card(id="c_1", x=50.0, y=50.0, stack_id="s_1")

    assert contained_card_ids(region, [stacked]) == []


def test_contained_card_ids_edge_touching_center_counts_as_inside():
    region = Region(id="r_1", x=0.0, y=0.0, width=200.0, height=120.0)
    card = Card(id="c_1", x=0.0, y=0.0)  # center exactly (100, 60), on no edge

    assert contained_card_ids(region, [card]) == ["c_1"]


def test_contained_stack_ids_uses_the_stacks_own_position():
    region = Region(id="r_1", x=0.0, y=0.0, width=300.0, height=200.0)
    inside = Stack(id="s_in", x=50.0, y=50.0)
    outside = Stack(id="s_out", x=1000.0, y=1000.0)

    assert contained_stack_ids(region, [inside, outside]) == ["s_in"]


def test_bounds_for_empty_selection_returns_minimum_size():
    x, y, width, height = bounds_for([], [])

    assert (width, height) == MIN_REGION_SIZE


def test_bounds_for_pads_around_cards_and_reserves_a_label_bar():
    card = Card(id="c_1", x=100.0, y=100.0)

    x, y, width, height = bounds_for([card], [], padding=24.0, label_bar=28.0)

    assert x == 100.0 - 24.0
    assert y == 100.0 - 24.0 - 28.0
    assert width >= MIN_REGION_SIZE[0]
    assert height >= MIN_REGION_SIZE[1]


def test_bounds_for_clamps_a_tiny_selection_to_the_minimum_size():
    card = Card(id="c_1", x=0.0, y=0.0)

    _x, _y, width, height = bounds_for([card], [], padding=0.0, label_bar=0.0)

    assert (width, height) == MIN_REGION_SIZE


def test_bounds_for_spans_multiple_cards_and_stacks():
    cards = [Card(id="c_1", x=0.0, y=0.0), Card(id="c_2", x=500.0, y=300.0)]
    stacks = [Stack(id="s_1", x=250.0, y=150.0)]

    x, y, width, height = bounds_for(cards, stacks, padding=10.0, label_bar=20.0)

    assert x == -10.0
    assert y == -30.0
    assert width >= 500.0 + 200.0 + 20.0
    assert height >= 300.0 + 120.0 + 40.0


def test_intersect_returns_the_overlap_rectangle():
    a = (0.0, 0.0, 300.0, 200.0)
    b = (200.0, 100.0, 300.0, 200.0)

    assert intersect(a, b) == (200.0, 100.0, 100.0, 100.0)


def test_intersect_touching_edges_is_not_an_overlap():
    a = (0.0, 0.0, 300.0, 200.0)
    b = (300.0, 0.0, 300.0, 200.0)  # touches a's right edge exactly

    assert intersect(a, b) is None


def test_intersect_disjoint_returns_none():
    a = (0.0, 0.0, 100.0, 100.0)
    b = (1000.0, 1000.0, 100.0, 100.0)

    assert intersect(a, b) is None


def test_margin_strips_centered_obstacle_gives_four_strips():
    outer = (0.0, 0.0, 400.0, 300.0)
    obstacle = (100.0, 100.0, 100.0, 100.0)

    strips = margin_strips(outer, obstacle)

    assert strips == [
        (0.0, 0.0, 100.0, 300.0),
        (200.0, 0.0, 200.0, 300.0),
        (0.0, 0.0, 400.0, 100.0),
        (0.0, 200.0, 400.0, 100.0),
    ]


def test_margin_strips_obstacle_touching_one_edge_omits_that_strip():
    outer = (0.0, 0.0, 400.0, 300.0)
    obstacle = (0.0, 100.0, 100.0, 100.0)  # touches outer's left edge

    strips = margin_strips(outer, obstacle)

    assert strips == [
        (100.0, 0.0, 300.0, 300.0),
        (0.0, 0.0, 400.0, 100.0),
        (0.0, 200.0, 400.0, 100.0),
    ]


def test_margin_strips_obstacle_spanning_one_axis_omits_those_strips():
    outer = (0.0, 0.0, 400.0, 300.0)
    obstacle = (0.0, 100.0, 400.0, 100.0)  # spans outer's full width

    assert margin_strips(outer, obstacle) == [(0.0, 0.0, 400.0, 100.0), (0.0, 200.0, 400.0, 100.0)]


def test_margin_strips_obstacle_fully_outside_returns_outer_unchanged():
    outer = (0.0, 0.0, 400.0, 300.0)
    obstacle = (1000.0, 1000.0, 50.0, 50.0)

    assert margin_strips(outer, obstacle) == [outer]


def test_margin_strips_obstacle_straddling_outers_boundary_clips_first():
    outer = (0.0, 0.0, 400.0, 300.0)
    obstacle = (350.0, 100.0, 200.0, 100.0)  # extends past outer's right edge

    strips = margin_strips(outer, obstacle)

    assert strips == [
        (0.0, 0.0, 350.0, 300.0),
        (0.0, 0.0, 400.0, 100.0),
        (0.0, 200.0, 400.0, 100.0),
    ]


def test_has_room_for_card_is_inclusive_at_the_minimum():
    min_w, min_h = CARD_CLEARANCE_SIZE
    assert has_room_for_card((0.0, 0.0, min_w, min_h)) is True
    assert has_room_for_card((0.0, 0.0, min_w - 1.0, min_h)) is False
    assert has_room_for_card((0.0, 0.0, min_w, min_h - 1.0)) is False


def test_translate_to_separate_pushes_along_the_smaller_overlap_axis():
    rect = (100.0, 100.0, 200.0, 120.0)
    obstacle = (0.0, 0.0, 300.0, 200.0)

    assert translate_to_separate(rect, obstacle) == (0.0, 100.0)


def test_translate_to_separate_no_overlap_returns_zero():
    rect = (1000.0, 1000.0, 200.0, 120.0)
    obstacle = (0.0, 0.0, 300.0, 200.0)

    assert translate_to_separate(rect, obstacle) == (0.0, 0.0)


def test_cards_in_any_region_no_regions_returns_empty_set():
    card = Card(id="c_1", x=50.0, y=50.0)

    assert cards_in_any_region([card], []) == set()


def test_cards_in_any_region_includes_a_card_inside_one_region():
    region = Region(id="r_1", x=0.0, y=0.0, width=300.0, height=200.0)
    inside = Card(id="c_in", x=50.0, y=50.0)
    outside = Card(id="c_out", x=1000.0, y=1000.0)

    assert cards_in_any_region([inside, outside], [region]) == {"c_in"}


def test_cards_in_any_region_no_duplicate_across_overlapping_regions():
    region_a = Region(id="r_a", x=0.0, y=0.0, width=300.0, height=200.0)
    region_b = Region(id="r_b", x=100.0, y=50.0, width=300.0, height=250.0)
    card = Card(id="c_1", x=110.0, y=60.0)  # inside both

    assert cards_in_any_region([card], [region_a, region_b]) == {"c_1"}


def test_cards_in_any_region_nothing_inside_returns_empty_set():
    region = Region(id="r_1", x=0.0, y=0.0, width=300.0, height=200.0)
    card = Card(id="c_1", x=1000.0, y=1000.0)

    assert cards_in_any_region([card], [region]) == set()


def test_stacks_in_any_region_includes_a_stack_inside_one_region():
    region = Region(id="r_1", x=0.0, y=0.0, width=300.0, height=200.0)
    inside = Stack(id="s_in", x=50.0, y=50.0)
    outside = Stack(id="s_out", x=1000.0, y=1000.0)

    assert stacks_in_any_region([inside, outside], [region]) == {"s_in"}


def test_stacks_in_any_region_no_regions_returns_empty_set():
    stack = Stack(id="s_1", x=50.0, y=50.0)

    assert stacks_in_any_region([stack], []) == set()


def test_to_corner_bbox_converts_xywh_to_two_corner_form():
    assert to_corner_bbox((10.0, 20.0, 100.0, 50.0)) == (10.0, 20.0, 110.0, 70.0)


def test_interior_rect_insets_by_gutter_and_label_bar():
    rect = (100.0, 200.0, 300.0, 250.0)

    x, y, width, height = interior_rect(rect)

    assert x == 100.0 + PLACEMENT_GUTTER
    assert y == 200.0 + LABEL_BAR_HEIGHT
    assert width == 300.0 - 2 * PLACEMENT_GUTTER
    assert height == 250.0 - LABEL_BAR_HEIGHT - PLACEMENT_GUTTER


def test_interior_rect_of_a_minimum_sized_region_exactly_fits_one_card():
    rect = (0.0, 0.0, MIN_REGION_SIZE[0], MIN_REGION_SIZE[1])

    _x, _y, width, height = interior_rect(rect)

    assert (width, height) == DEFAULT_CARD_SIZE
