from indexcards.models.card import Card
from indexcards.models.region import Region
from indexcards.models.stack import Stack
from indexcards.regions.drag import carried_by_region, region_drag_group


def _outer_inner_and_overlapping():
    return [
        Region(id="outer", x=0.0, y=0.0, width=900.0, height=700.0),
        Region(id="inner", x=300.0, y=250.0, width=320.0, height=300.0),
        Region(id="b", x=800.0, y=100.0, width=700.0, height=500.0),  # overlaps outer's right edge
    ]


def test_drag_group_is_the_selection_plus_everything_it_fully_contains():
    regions = _outer_inner_and_overlapping()

    assert region_drag_group(["outer"], regions) == ["inner", "outer"]  # smallest first
    assert region_drag_group(["inner"], regions) == ["inner"]
    assert region_drag_group(["b"], regions) == ["b"]  # overlapping isn't containing


def test_drag_group_dedupes_a_selection_that_already_includes_the_child():
    regions = _outer_inner_and_overlapping()

    assert region_drag_group(["outer", "inner"], regions) == ["inner", "outer"]


def test_drag_group_includes_grandchildren():
    regions = [
        Region(id="a", x=0.0, y=0.0, width=1200.0, height=900.0),
        Region(id="b", x=100.0, y=100.0, width=800.0, height=600.0),
        Region(id="c", x=200.0, y=200.0, width=300.0, height=250.0),
    ]

    assert region_drag_group(["a"], regions) == ["c", "b", "a"]


def test_a_card_in_both_inner_and_outer_is_owned_by_the_inner_region():
    regions = _outer_inner_and_overlapping()
    cards = [Card(id="in_inner", x=330.0, y=300.0), Card(id="outer_only", x=40.0, y=60.0)]
    group = region_drag_group(["outer"], regions)

    card_ids, _ = carried_by_region(group, regions, cards, [], carry_overlap_items=False)

    assert card_ids == {"inner": ["in_inner"], "outer": ["outer_only"]}


def test_dragging_the_inner_region_alone_carries_only_its_own_cards():
    regions = _outer_inner_and_overlapping()
    cards = [Card(id="in_inner", x=330.0, y=300.0), Card(id="outer_only", x=40.0, y=60.0)]

    card_ids, _ = carried_by_region(["inner"], regions, cards, [], carry_overlap_items=False)

    assert card_ids == {"inner": ["in_inner"]}  # nested isn't an overlap: still carried


def test_stay_mode_leaves_cards_in_an_overlap_with_an_undragged_region_behind():
    regions = _outer_inner_and_overlapping()
    cards = [
        Card(id="outer_only", x=40.0, y=60.0),
        Card(id="shared", x=720.0, y=200.0),  # center (820, 260): in outer AND b
    ]
    group = region_drag_group(["outer"], regions)

    card_ids, _ = carried_by_region(group, regions, cards, [], carry_overlap_items=False)

    assert card_ids["outer"] == ["outer_only"]


def test_drag_mode_carries_cards_in_an_overlap():
    regions = _outer_inner_and_overlapping()
    cards = [Card(id="shared", x=720.0, y=200.0)]
    group = region_drag_group(["outer"], regions)

    card_ids, _ = carried_by_region(group, regions, cards, [], carry_overlap_items=True)

    assert card_ids["outer"] == ["shared"]


def test_a_card_in_an_overlap_moves_when_both_overlapping_regions_are_dragged():
    regions = _outer_inner_and_overlapping()
    cards = [Card(id="shared", x=720.0, y=200.0)]
    group = region_drag_group(["outer", "b"], regions)

    card_ids, _ = carried_by_region(group, regions, cards, [], carry_overlap_items=False)

    assert [cid for ids in card_ids.values() for cid in ids] == ["shared"]


def test_stacks_follow_the_same_rules_and_stacked_cards_are_ignored():
    regions = _outer_inner_and_overlapping()
    cards = [Card(id="stacked", x=40.0, y=60.0, stack_id="s_1")]
    stacks = [
        Stack(id="s_only", x=40.0, y=500.0),
        Stack(id="s_shared", x=720.0, y=200.0),
    ]
    group = region_drag_group(["outer"], regions)

    card_ids, stack_ids = carried_by_region(
        group, regions, cards, stacks, carry_overlap_items=False
    )

    assert card_ids["outer"] == []
    assert stack_ids["outer"] == ["s_only"]
