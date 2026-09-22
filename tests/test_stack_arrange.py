import random

from indexcards.arrange.auto_arrange import positions_bbox
from indexcards.arrange.stack_arrange import compute_explode_layout
from indexcards.models.card import Card
from indexcards.models.region import Region
from indexcards.models.stack import Stack


def _member_cards() -> list[Card]:
    return [Card(id="c_1"), Card(id="c_2"), Card(id="c_3")]


def test_compute_explode_layout_covers_every_member_card():
    stack = Stack(id="s_1", x=100.0, y=100.0)
    positions = compute_explode_layout(stack, _member_cards(), "tile", {}, {})
    assert set(positions) == {"c_1", "c_2", "c_3"}


def test_compute_explode_layout_anchors_at_stack_position_when_no_obstacles():
    stack = Stack(id="s_1", x=500.0, y=500.0)
    positions = compute_explode_layout(
        stack, _member_cards(), "tile", {}, {}, rng=random.Random(0)
    )
    bbox = positions_bbox(positions)
    # No obstacles to avoid, so the layout should sit right where it was
    # anchored (tile always starts its first cell at the anchor).
    assert bbox[0] == 500.0
    assert bbox[1] == 500.0


def test_compute_explode_layout_avoids_other_cards_and_stacks():
    stack = Stack(id="s_1", x=0.0, y=0.0)
    other_card_positions = {"c_other": (0.0, 0.0)}
    other_stack_positions = {"s_other": (0.0, 0.0)}
    positions = compute_explode_layout(
        stack,
        _member_cards(),
        "tile",
        other_card_positions,
        other_stack_positions,
        rng=random.Random(0),
    )
    layout_bbox = positions_bbox(positions)
    obstacle_bbox = positions_bbox({**other_card_positions, **other_stack_positions})
    no_overlap = (
        layout_bbox[2] <= obstacle_bbox[0]
        or layout_bbox[0] >= obstacle_bbox[2]
        or layout_bbox[3] <= obstacle_bbox[1]
        or layout_bbox[1] >= obstacle_bbox[3]
    )
    assert no_overlap


def test_compute_explode_layout_scatter_group_by_covers_every_member_card():
    stack = Stack(id="s_1", x=0.0, y=0.0)
    positions = compute_explode_layout(
        stack, _member_cards(), "scatter", {}, {}, rng=random.Random(3)
    )
    assert set(positions) == {"c_1", "c_2", "c_3"}


def test_compute_explode_layout_avoids_a_region_it_would_otherwise_land_on():
    stack = Stack(id="s_1", x=0.0, y=0.0)
    region = Region(id="r_1", x=0.0, y=0.0, width=300.0, height=300.0)

    positions = compute_explode_layout(
        stack, _member_cards(), "tile", {}, {}, rng=random.Random(0), regions=[region]
    )

    layout_bbox = positions_bbox(positions)
    region_bbox = (0.0, 0.0, 300.0, 300.0)
    no_overlap = (
        layout_bbox[2] <= region_bbox[0]
        or layout_bbox[0] >= region_bbox[2]
        or layout_bbox[3] <= region_bbox[1]
        or layout_bbox[1] >= region_bbox[3]
    )
    assert no_overlap
