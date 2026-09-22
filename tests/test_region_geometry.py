from indexcards.models.card import Card
from indexcards.models.region import MIN_REGION_SIZE, Region
from indexcards.models.stack import Stack
from indexcards.regions.geometry import bounds_for, contained_card_ids, contained_stack_ids


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
