from __future__ import annotations

from indexcards.models.card import DEFAULT_CARD_SIZE, Card
from indexcards.models.region import MIN_REGION_SIZE, Region
from indexcards.models.stack import Stack

_LABEL_BAR_HEIGHT = 28.0
_PADDING = 24.0


def _card_center(card: Card) -> tuple[float, float]:
    width, height = DEFAULT_CARD_SIZE
    return (card.x + width / 2, card.y + height / 2)


def _stack_center(stack: Stack) -> tuple[float, float]:
    width, height = DEFAULT_CARD_SIZE
    return (stack.x + width / 2, stack.y + height / 2)


def _contains(region: Region, point: tuple[float, float]) -> bool:
    px, py = point
    return region.x <= px <= region.x + region.width and region.y <= py <= region.y + region.height


def contained_card_ids(region: Region, cards) -> list[str]:
    """Loose cards (stack_id is None) whose center falls within region's
    rectangle -- membership is derived, never stored. A stacked card rides
    with its Stack instead, since it has no position of its own."""
    return [
        card.id for card in cards if card.stack_id is None and _contains(region, _card_center(card))
    ]


def contained_stack_ids(region: Region, stacks) -> list[str]:
    return [stack.id for stack in stacks if _contains(region, _stack_center(stack))]


def bounds_for(cards, stacks, padding: float = _PADDING, label_bar: float = _LABEL_BAR_HEIGHT):
    """A region rect that snugly contains every given card/stack, with
    padding on all sides and extra headroom for the label bar, clamped to
    MIN_REGION_SIZE. Returns (x, y, width, height)."""
    card_w, card_h = DEFAULT_CARD_SIZE
    lefts, tops, rights, bottoms = [], [], [], []
    for card in cards:
        lefts.append(card.x)
        tops.append(card.y)
        rights.append(card.x + card_w)
        bottoms.append(card.y + card_h)
    for stack in stacks:
        lefts.append(stack.x)
        tops.append(stack.y)
        rights.append(stack.x + card_w)
        bottoms.append(stack.y + card_h)

    if not lefts:
        min_w, min_h = MIN_REGION_SIZE
        return (0.0, 0.0, min_w, min_h)

    left, top, right, bottom = min(lefts), min(tops), max(rights), max(bottoms)
    x = left - padding
    y = top - padding - label_bar
    width = max((right - left) + 2 * padding, MIN_REGION_SIZE[0])
    height = max((bottom - top) + 2 * padding + label_bar, MIN_REGION_SIZE[1])
    return (x, y, width, height)
