import random

import pytest

from indexcards.arrange.region_arrange import arrange_with_regions
from indexcards.models.card import DEFAULT_CARD_SIZE, Card
from indexcards.models.link import Link
from indexcards.models.region import Region
from indexcards.models.stack import Stack
from indexcards.regions.geometry import intersect, to_rect

CARD_W, CARD_H = DEFAULT_CARD_SIZE


def _apply(cards, stacks, regions, result):
    cards = [
        Card(id=c.id, x=result.card_positions.get(c.id, (c.x, c.y))[0],
             y=result.card_positions.get(c.id, (c.x, c.y))[1], pinned=c.pinned)
        for c in cards
    ]
    stacks = [
        Stack(id=s.id, x=result.stack_positions.get(s.id, (s.x, s.y))[0],
              y=result.stack_positions.get(s.id, (s.x, s.y))[1])
        for s in stacks
    ]
    regions = [
        Region(id=r.id, x=result.region_geometries.get(r.id, to_rect(r))[0],
               y=result.region_geometries.get(r.id, to_rect(r))[1],
               width=result.region_geometries.get(r.id, to_rect(r))[2],
               height=result.region_geometries.get(r.id, to_rect(r))[3], label=r.label)
        for r in regions
    ]
    return cards, stacks, regions


def _card_rect(card):
    return (card.x, card.y, CARD_W, CARD_H)


def _fully_inside(card, region):
    x, y, w, h = to_rect(region)
    return x <= card.x and card.x + CARD_W <= x + w and y <= card.y and card.y + CARD_H <= y + h


def test_tile_lays_region_members_inside_the_region_at_its_interior_corner():
    region = Region(id="r", x=0.0, y=0.0, width=800.0, height=500.0)
    cards = [Card(id=f"c{i}", x=100.0 + i, y=100.0 + i) for i in range(3)]

    result = arrange_with_regions(cards, [], [region], "tile")

    assert result is not None
    assert result.region_geometries == {}  # fits already, so no growth
    placed, _, _ = _apply(cards, [], [region], result)
    assert all(_fully_inside(c, region) for c in placed)
    assert min((c.x, c.y) for c in placed) == (16.0, 44.0)


def test_overflowing_region_grows_and_never_shrinks():
    region = Region(id="r", x=0.0, y=0.0, width=300.0, height=300.0)
    cards = [Card(id=f"c{i}", x=50.0, y=50.0) for i in range(6)]

    result = arrange_with_regions(cards, [], [region], "tile")

    x, y, w, h = result.region_geometries["r"]
    assert (x, y) == (0.0, 0.0)
    assert w >= 300.0 and h >= 300.0 and (w > 300.0 or h > 300.0)
    placed, _, regions = _apply(cards, [], [region], result)
    assert all(_fully_inside(c, regions[0]) for c in placed)


def test_a_roomy_region_is_not_shrunk():
    region = Region(id="r", x=0.0, y=0.0, width=2000.0, height=1500.0)
    cards = [Card(id="c", x=10.0, y=10.0)]

    result = arrange_with_regions(cards, [], [region], "tile")

    assert "r" not in result.region_geometries


def test_empty_region_and_no_cards_is_untouched():
    region = Region(id="r", x=0.0, y=0.0, width=400.0, height=300.0)
    result = arrange_with_regions([], [], [region], "tile")
    assert result.card_positions == {} and result.region_geometries == {}


def test_nested_region_moves_as_a_rigid_block_with_its_cards():
    outer = Region(id="outer", x=0.0, y=0.0, width=900.0, height=700.0)
    inner = Region(id="inner", x=500.0, y=300.0, width=300.0, height=250.0)
    cards = [Card(id="loose", x=40.0, y=60.0), Card(id="in_a", x=520.0, y=340.0)]

    result = arrange_with_regions(cards, [], [outer, inner], "tile")

    placed, _, regions = _apply(cards, [], [outer, inner], result)
    by_id = {c.id: c for c in placed}
    new_inner = {r.id: r for r in regions}["inner"]
    assert (new_inner.width, new_inner.height) == (300.0, 250.0)  # size unchanged
    # The inner card sits at the same spot relative to its region as
    # before the block moved (it was laid out at the inner's own corner).
    assert (by_id["in_a"].x - new_inner.x, by_id["in_a"].y - new_inner.y) == (16.0, 44.0)
    assert intersect(_card_rect(by_id["loose"]), to_rect(new_inner)) is None
    assert _fully_inside(by_id["in_a"], new_inner)


def test_inner_region_grows_to_hold_its_own_laid_out_cards():
    outer = Region(id="outer", x=0.0, y=0.0, width=1400.0, height=900.0)
    inner = Region(id="inner", x=500.0, y=300.0, width=300.0, height=250.0)
    cards = [Card(id=f"i{i}", x=520.0 + i, y=340.0) for i in range(3)]

    result = arrange_with_regions(cards, [], [outer, inner], "tile")

    placed, _, regions = _apply(cards, [], [outer, inner], result)
    new_inner = {r.id: r for r in regions}["inner"]
    assert all(_fully_inside(c, new_inner) for c in placed)
    assert new_inner.width > 300.0 or new_inner.height > 250.0


def test_card_in_a_partial_overlap_stays_put():
    a = Region(id="a", x=0.0, y=0.0, width=700.0, height=500.0)
    b = Region(id="b", x=400.0, y=100.0, width=700.0, height=500.0)
    frozen = Card(id="frozen", x=450.0, y=200.0)  # center inside both
    member = Card(id="member", x=30.0, y=40.0)  # only in a

    result = arrange_with_regions([frozen, member], [], [a, b], "tile")

    assert "frozen" not in result.card_positions


def test_pinned_card_and_stack_inside_a_region_stay_put():
    region = Region(id="r", x=0.0, y=0.0, width=900.0, height=600.0)
    pinned = Card(id="p", x=600.0, y=300.0, pinned=True)
    stack = Stack(id="s", x=300.0, y=300.0)
    loose = [Card(id=f"c{i}", x=20.0 + i, y=40.0) for i in range(4)]

    result = arrange_with_regions([pinned, *loose], [stack], [region], "tile")

    assert "p" not in result.card_positions and "s" not in result.stack_positions
    placed, stacks, _ = _apply([pinned, *loose], [stack], [region], result)
    rects = [_card_rect(c) for c in placed] + [(stacks[0].x, stacks[0].y, CARD_W, CARD_H)]
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            assert intersect(a, b) is None


def test_pinned_free_card_is_left_alone_and_free_cards_clear_regions():
    region = Region(id="r", x=0.0, y=0.0, width=400.0, height=300.0)
    pinned = Card(id="p", x=5000.0, y=5000.0, pinned=True)
    free = [Card(id=f"f{i}", x=1000.0 + 10.0 * i, y=1000.0) for i in range(4)]

    result = arrange_with_regions([pinned, *free], [], [region], "tile")

    assert "p" not in result.card_positions
    placed, _, _ = _apply([pinned, *free], [], [region], result)
    for card in placed[1:]:
        assert intersect(_card_rect(card), to_rect(region)) is None


def test_ignore_pinned_moves_pinned_cards():
    region = Region(id="r", x=0.0, y=0.0, width=800.0, height=500.0)
    pinned = Card(id="p", x=300.0, y=200.0, pinned=True)

    result = arrange_with_regions([pinned], [], [region], "tile", ignore_pinned=True)

    assert result.card_positions["p"] == (16.0, 44.0)


def test_untangle_uses_each_regions_own_links():
    region = Region(id="r", x=0.0, y=0.0, width=900.0, height=600.0)
    cards = [Card(id=f"c{i}", x=100.0, y=100.0) for i in range(3)]
    links = [Link(id="l", source="c0", target="c1")]

    result = arrange_with_regions(cards, [], [region], "untangle", links=links)

    placed, _, regions = _apply(cards, [], [region], result)
    assert all(_fully_inside(c, regions[0]) for c in placed)


@pytest.mark.parametrize("mode", ["tile", "columns_alphabetical", "scatter"])
def test_randomized_layouts_keep_every_card_inside_or_outside_and_regions_valid(mode):
    rng = random.Random(1234)
    for _ in range(40):
        regions = [
            Region(id="outer", x=0.0, y=0.0, width=rng.uniform(900, 1200),
                   height=rng.uniform(650, 900)),
            Region(id="side", x=2000.0, y=0.0, width=rng.uniform(300, 700),
                   height=rng.uniform(250, 500)),
        ]
        regions.append(Region(id="inner", x=600.0, y=350.0, width=rng.uniform(260, 320),
                              height=rng.uniform(200, 260)))
        cards = []
        for i in range(rng.randint(1, 9)):
            cards.append(Card(id=f"o{i}", x=rng.uniform(20, 150), y=rng.uniform(40, 150)))
        for i in range(rng.randint(0, 6)):
            cards.append(Card(id=f"s{i}", x=2020 + rng.uniform(0, 50), y=40 + rng.uniform(0, 50)))
        for i in range(rng.randint(0, 6)):
            cards.append(Card(id=f"f{i}", x=6000 + i, y=6000 + i))

        result = arrange_with_regions(cards, [], regions, mode)
        if result is None:
            continue
        placed, _, final_regions = _apply(cards, [], regions, result)
        for region in final_regions:
            for card in placed:
                if intersect(_card_rect(card), to_rect(region)) is not None:
                    # Overlapping a region at all means fully inside it
                    # (no straddling), or being one of a nested pair's cards.
                    assert _fully_inside(card, region), (mode, card.id, region.id)
        if mode != "scatter":  # scatter tolerates a small overlap by design
            for i, a in enumerate(placed):
                for b in placed[i + 1:]:
                    assert intersect(_card_rect(a), _card_rect(b)) is None, (mode, a.id, b.id)
