import math
import random

from indexcards.arrange.auto_arrange import positions_bbox
from indexcards.arrange.link_arrange import (
    arrange_by_untangle_links,
    arrange_untangle_from_card,
)
from indexcards.models.card import DEFAULT_CARD_SIZE, Card
from indexcards.models.link import Link


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def test_untangle_links_covers_every_card():
    cards = [Card(id=f"c_{i}") for i in range(6)]
    links = [
        Link(id="l_1", source="c_0", target="c_1"),
        Link(id="l_2", source="c_1", target="c_2"),
    ]
    positions = arrange_by_untangle_links(cards, links, rng=random.Random(0))
    assert set(positions) == {c.id for c in cards}


def test_untangle_links_spreads_out_a_linked_component():
    # A 4-cycle, all crammed into the exact same starting position -- a
    # force-directed layout should spread every pair of them well clear
    # of each other's full card footprint, not leave them overlapping.
    cards = [Card(id=f"c_{i}", x=0.0, y=0.0) for i in range(4)]
    links = [
        Link(id="l_1", source="c_0", target="c_1"),
        Link(id="l_2", source="c_1", target="c_2"),
        Link(id="l_3", source="c_2", target="c_3"),
        Link(id="l_4", source="c_3", target="c_0"),
    ]
    positions = arrange_by_untangle_links(cards, links, rng=random.Random(0))

    width, height = DEFAULT_CARD_SIZE
    min_clearance = min(width, height) * 0.5
    values = list(positions.values())
    for i, a in enumerate(values):
        for b in values[i + 1 :]:
            assert _dist(a, b) >= min_clearance


def test_untangle_links_puts_isolated_cards_in_their_own_tile_block():
    cards = [Card(id="c_1"), Card(id="c_2"), Card(id="c_3"), Card(id="c_4")]
    links = [Link(id="l_1", source="c_1", target="c_2")]
    positions = arrange_by_untangle_links(cards, links, rng=random.Random(0))

    linked_bbox = positions_bbox({cid: positions[cid] for cid in ("c_1", "c_2")})
    isolated_bbox = positions_bbox({cid: positions[cid] for cid in ("c_3", "c_4")})
    # The isolated block sits clear of the linked cluster's bounding box
    # (placed to its right, per arrange_by_untangle_links' own docstring).
    assert isolated_bbox[0] >= linked_bbox[2]


def test_untangle_links_with_no_links_is_just_a_tile():
    cards = [Card(id="c_1"), Card(id="c_2"), Card(id="c_3")]
    positions = arrange_by_untangle_links(cards, [], rng=random.Random(0))
    assert set(positions) == {"c_1", "c_2", "c_3"}


def test_untangle_links_with_no_cards_returns_empty():
    assert arrange_by_untangle_links([], []) == {}


def test_untangle_from_card_only_touches_its_own_component():
    # Two separate link chains -- untangling from c_1 must never move
    # anything in the unrelated c_3/c_4 chain.
    cards = [
        Card(id="c_1", x=0.0, y=0.0),
        Card(id="c_2", x=10.0, y=0.0),
        Card(id="c_3", x=500.0, y=500.0),
        Card(id="c_4", x=510.0, y=500.0),
    ]
    links = [
        Link(id="l_1", source="c_1", target="c_2"),
        Link(id="l_2", source="c_3", target="c_4"),
    ]
    positions = arrange_untangle_from_card("c_1", cards, links, rng=random.Random(0))
    assert set(positions) == {"c_1", "c_2"}


def test_untangle_from_card_reanchors_near_the_components_current_centroid():
    cards = [
        Card(id="c_1", x=1000.0, y=1000.0),
        Card(id="c_2", x=1000.0, y=1000.0),
        Card(id="c_3", x=1000.0, y=1000.0),
    ]
    links = [
        Link(id="l_1", source="c_1", target="c_2"),
        Link(id="l_2", source="c_2", target="c_3"),
    ]
    positions = arrange_untangle_from_card("c_1", cards, links, rng=random.Random(0))

    result_cx = sum(x for x, _y in positions.values()) / len(positions)
    result_cy = sum(y for _x, y in positions.values()) / len(positions)
    # Started clustered at (1000, 1000) -- the untangled result should
    # still be centered near there, not relocated across the canvas.
    assert abs(result_cx - 1000.0) < 300.0
    assert abs(result_cy - 1000.0) < 300.0


def test_untangle_from_card_with_no_links_is_a_noop():
    cards = [Card(id="c_1"), Card(id="c_2")]
    assert arrange_untangle_from_card("c_1", cards, []) == {}


def test_untangle_from_card_excludes_pinned_members():
    cards = [
        Card(id="c_1", pinned=True),
        Card(id="c_2"),
        Card(id="c_3"),
    ]
    links = [
        Link(id="l_1", source="c_1", target="c_2"),
        Link(id="l_2", source="c_2", target="c_3"),
    ]
    positions = arrange_untangle_from_card("c_2", cards, links, rng=random.Random(0))
    assert "c_1" not in positions
    assert set(positions) == {"c_2", "c_3"}


def test_untangle_from_card_unknown_card_returns_empty():
    cards = [Card(id="c_1")]
    assert arrange_untangle_from_card("nonexistent", cards, []) == {}
