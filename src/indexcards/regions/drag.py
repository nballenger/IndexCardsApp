from __future__ import annotations

from collections.abc import Iterable

from indexcards.models.card import DEFAULT_CARD_SIZE, Card
from indexcards.models.region import Region
from indexcards.models.stack import Stack
from indexcards.regions.geometry import contains_point, relationship, to_rect

# Settings values for "when dragging a Region, cards in overlaps with other
# Regions should ..." (app_settings.REGION_DRAG_OVERLAP_CARDS_OPTIONS).
OVERLAP_CARDS_DRAG = "drag"
OVERLAP_CARDS_STAY = "stay"


def region_drag_group(selected_ids: Iterable[str], regions: Iterable[Region]) -> list[str]:
    """The regions that move when `selected_ids` are dragged: the selection
    plus every region fully contained by one of them (recursively) -- an
    inner region rides along as a child of the outer one. Ordered smallest
    area first (ties by id), so the innermost region comes first."""
    region_list = list(regions)
    rects = {region.id: to_rect(region) for region in region_list}
    group: set[str] = {rid for rid in selected_ids if rid in rects}
    frontier = list(group)
    while frontier:
        outer = frontier.pop()
        for rid, rect in rects.items():
            if rid in group:
                continue
            if relationship(rects[outer], rect) == "a_contains_b":
                group.add(rid)
                frontier.append(rid)
    return sorted(group, key=lambda rid: (rects[rid][2] * rects[rid][3], rid))


def carried_by_region(
    group_ids: list[str],
    regions: Iterable[Region],
    cards: Iterable[Card],
    stacks: Iterable[Stack],
    carry_overlap_items: bool,
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Which loose cards and stacks travel with each dragged region, as
    ({region_id: [card_id, ...]}, {region_id: [stack_id, ...]}) -- every
    item is assigned to exactly one region (the smallest dragged region
    whose rectangle holds its center), so nothing is moved twice.

    An item whose center is in a dragged region is normally carried. With
    carry_overlap_items False, an item that is ALSO in a region that isn't
    being dragged and only partially overlaps the dragged one (i.e. it sits
    in an overlap) stays where it is -- a region being dragged must not
    steal what the other region also holds. Containment isn't an overlap:
    a card inside both an inner region and its outer region is simply
    carried by whichever of them moves."""
    region_list = list(regions)
    rects = {region.id: to_rect(region) for region in region_list}
    in_group = set(group_ids)
    card_width, card_height = DEFAULT_CARD_SIZE

    def owner(x: float, y: float) -> str | None:
        center = (x + card_width / 2, y + card_height / 2)
        containing = [rid for rid, rect in rects.items() if contains_point(rect, center)]
        dragged = [rid for rid in group_ids if rid in containing]
        if not dragged:
            return None
        if not carry_overlap_items:
            others = [rid for rid in containing if rid not in in_group]
            for other in others:
                if any(relationship(rects[other], rects[rid]) == "overlap" for rid in dragged):
                    return None
        return dragged[0]

    card_ids: dict[str, list[str]] = {rid: [] for rid in group_ids}
    stack_ids: dict[str, list[str]] = {rid: [] for rid in group_ids}
    for card in cards:
        if card.stack_id is not None:
            continue
        rid = owner(card.x, card.y)
        if rid is not None:
            card_ids[rid].append(card.id)
    for stack in stacks:
        rid = owner(stack.x, stack.y)
        if rid is not None:
            stack_ids[rid].append(stack.id)
    return card_ids, stack_ids
