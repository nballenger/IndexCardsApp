from __future__ import annotations

from indexcards.models.card import DEFAULT_CARD_SIZE, Card


def align_horizontal_midline(cards: list[Card]) -> dict[str, tuple[float, float]]:
    """Moves every card's y so its own horizontal midline (a left-right
    line through its vertical center) lands on the selection's shared
    one -- the vertical midpoint of the selection's bounding box, not a
    plain average of individual centers, so a lone outlier doesn't pull
    the line disproportionately. x is untouched."""
    _width, height = DEFAULT_CARD_SIZE
    centers_y = [card.y + height / 2 for card in cards]
    target_center_y = (min(centers_y) + max(centers_y)) / 2
    return {card.id: (card.x, target_center_y - height / 2) for card in cards}


def align_vertical_midline(cards: list[Card]) -> dict[str, tuple[float, float]]:
    """Moves every card's x so its own vertical midline (a top-bottom
    line through its horizontal center) lands on the selection's shared
    one -- the horizontal midpoint of the selection's bounding box. y is
    untouched."""
    width, _height = DEFAULT_CARD_SIZE
    centers_x = [card.x + width / 2 for card in cards]
    target_center_x = (min(centers_x) + max(centers_x)) / 2
    return {card.id: (target_center_x - width / 2, card.y) for card in cards}


def distribute_horizontal(cards: list[Card]) -> dict[str, tuple[float, float]]:
    """Evenly spaces every card's x between the leftmost and rightmost
    card's own x (both stay fixed), leaving y untouched. Every card is
    the same size, so spacing left edges evenly is equivalent to
    spacing centers (or any other fixed reference point) evenly -- the
    gaps between adjacent cards end up equal either way. Fewer than 3
    cards has nothing to distribute in the middle, so every card's
    position is returned unchanged."""
    if len(cards) < 3:
        return {card.id: (card.x, card.y) for card in cards}
    ordered = sorted(cards, key=lambda card: card.x)
    left_x, right_x = ordered[0].x, ordered[-1].x
    step = (right_x - left_x) / (len(ordered) - 1)
    return {card.id: (left_x + i * step, card.y) for i, card in enumerate(ordered)}


def distribute_vertical(cards: list[Card]) -> dict[str, tuple[float, float]]:
    """Evenly spaces every card's y between the topmost and bottommost
    card's own y (both stay fixed), leaving x untouched -- see
    distribute_horizontal for why equal-spacing needs no special
    handling for card size."""
    if len(cards) < 3:
        return {card.id: (card.x, card.y) for card in cards}
    ordered = sorted(cards, key=lambda card: card.y)
    top_y, bottom_y = ordered[0].y, ordered[-1].y
    step = (bottom_y - top_y) / (len(ordered) - 1)
    return {card.id: (card.x, top_y + i * step) for i, card in enumerate(ordered)}
