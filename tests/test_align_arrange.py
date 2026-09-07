from indexcards.arrange.align_arrange import (
    align_horizontal_midline,
    align_vertical_midline,
    distribute_horizontal,
    distribute_vertical,
)
from indexcards.models.card import DEFAULT_CARD_SIZE, Card

WIDTH, HEIGHT = DEFAULT_CARD_SIZE


def test_align_horizontal_midline_gives_every_card_the_same_center_y():
    cards = [
        Card(id="c_1", x=0.0, y=0.0),
        Card(id="c_2", x=100.0, y=200.0),
        Card(id="c_3", x=300.0, y=50.0),
    ]
    positions = align_horizontal_midline(cards)

    centers_y = {y + HEIGHT / 2 for _x, y in positions.values()}
    assert len(centers_y) == 1


def test_align_horizontal_midline_leaves_x_unchanged():
    cards = [Card(id="c_1", x=10.0, y=0.0), Card(id="c_2", x=250.0, y=400.0)]
    positions = align_horizontal_midline(cards)
    assert positions["c_1"][0] == 10.0
    assert positions["c_2"][0] == 250.0


def test_align_horizontal_midline_uses_the_bounding_box_center_not_the_average():
    # Outlier at y=1000 shouldn't drag the line toward the mean of all
    # three -- it's the midpoint of the min/max extremes only.
    cards = [
        Card(id="c_1", x=0.0, y=0.0),
        Card(id="c_2", x=0.0, y=10.0),
        Card(id="c_3", x=0.0, y=1000.0),
    ]
    positions = align_horizontal_midline(cards)
    expected_center_y = (0.0 + HEIGHT / 2 + 1000.0 + HEIGHT / 2) / 2
    for _x, y in positions.values():
        assert y + HEIGHT / 2 == expected_center_y


def test_align_vertical_midline_gives_every_card_the_same_center_x():
    cards = [
        Card(id="c_1", x=0.0, y=0.0),
        Card(id="c_2", x=200.0, y=100.0),
        Card(id="c_3", x=50.0, y=300.0),
    ]
    positions = align_vertical_midline(cards)

    centers_x = {x + WIDTH / 2 for x, _y in positions.values()}
    assert len(centers_x) == 1


def test_align_vertical_midline_leaves_y_unchanged():
    cards = [Card(id="c_1", x=0.0, y=10.0), Card(id="c_2", x=400.0, y=250.0)]
    positions = align_vertical_midline(cards)
    assert positions["c_1"][1] == 10.0
    assert positions["c_2"][1] == 250.0


def test_distribute_horizontal_keeps_the_extremes_fixed():
    cards = [
        Card(id="c_left", x=0.0, y=0.0),
        Card(id="c_mid", x=900.0, y=0.0),
        Card(id="c_right", x=999.0, y=0.0),
    ]
    positions = distribute_horizontal(cards)
    assert positions["c_left"][0] == 0.0
    assert positions["c_right"][0] == 999.0


def test_distribute_horizontal_spaces_the_middle_cards_evenly():
    cards = [
        Card(id="c_0", x=0.0, y=0.0),
        Card(id="c_1", x=10.0, y=0.0),
        Card(id="c_2", x=20.0, y=0.0),
        Card(id="c_3", x=900.0, y=0.0),
    ]
    positions = distribute_horizontal(cards)
    xs = sorted(x for x, _y in positions.values())
    gaps = [b - a for a, b in zip(xs, xs[1:], strict=False)]
    assert gaps[0] == gaps[1] == gaps[2]
    assert xs[0] == 0.0
    assert xs[-1] == 900.0


def test_distribute_horizontal_leaves_y_unchanged():
    cards = [
        Card(id="c_1", x=0.0, y=5.0),
        Card(id="c_2", x=50.0, y=15.0),
        Card(id="c_3", x=100.0, y=25.0),
    ]
    positions = distribute_horizontal(cards)
    assert positions["c_1"][1] == 5.0
    assert positions["c_2"][1] == 15.0
    assert positions["c_3"][1] == 25.0


def test_distribute_horizontal_with_fewer_than_three_cards_is_a_noop():
    cards = [Card(id="c_1", x=10.0, y=20.0), Card(id="c_2", x=300.0, y=40.0)]
    positions = distribute_horizontal(cards)
    assert positions["c_1"] == (10.0, 20.0)
    assert positions["c_2"] == (300.0, 40.0)


def test_distribute_vertical_keeps_the_extremes_fixed():
    cards = [
        Card(id="c_top", x=0.0, y=0.0),
        Card(id="c_mid", x=0.0, y=900.0),
        Card(id="c_bottom", x=0.0, y=999.0),
    ]
    positions = distribute_vertical(cards)
    assert positions["c_top"][1] == 0.0
    assert positions["c_bottom"][1] == 999.0


def test_distribute_vertical_spaces_the_middle_cards_evenly():
    cards = [
        Card(id="c_0", x=0.0, y=0.0),
        Card(id="c_1", x=0.0, y=10.0),
        Card(id="c_2", x=0.0, y=20.0),
        Card(id="c_3", x=0.0, y=900.0),
    ]
    positions = distribute_vertical(cards)
    ys = sorted(y for _x, y in positions.values())
    gaps = [b - a for a, b in zip(ys, ys[1:], strict=False)]
    assert gaps[0] == gaps[1] == gaps[2]


def test_distribute_vertical_leaves_x_unchanged():
    cards = [
        Card(id="c_1", x=5.0, y=0.0),
        Card(id="c_2", x=15.0, y=50.0),
        Card(id="c_3", x=25.0, y=100.0),
    ]
    positions = distribute_vertical(cards)
    assert positions["c_1"][0] == 5.0
    assert positions["c_2"][0] == 15.0
    assert positions["c_3"][0] == 25.0


def test_distribute_vertical_with_fewer_than_three_cards_is_a_noop():
    cards = [Card(id="c_1", x=10.0, y=20.0), Card(id="c_2", x=30.0, y=400.0)]
    positions = distribute_vertical(cards)
    assert positions["c_1"] == (10.0, 20.0)
    assert positions["c_2"] == (30.0, 400.0)
