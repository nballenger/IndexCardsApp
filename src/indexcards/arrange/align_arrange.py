from __future__ import annotations

from indexcards.arrange.auto_arrange import TILE_GUTTER
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
    card's own x, leaving y untouched. Every card is the same size, so
    spacing left edges evenly is equivalent to spacing centers (or any
    other fixed reference point) evenly -- the gaps between adjacent
    cards end up equal either way.

    The leftmost and rightmost cards stay fixed only when the
    selection's own spread already leaves at least TILE_GUTTER of
    clearance between adjacent cards at that spacing (matching Tile's
    own default gutter). When it doesn't -- most visibly, a fully
    overlapping stack, where distributing "between the extremes" would
    otherwise be a no-op since every card starts at the same x -- the
    step is widened to width + TILE_GUTTER instead, and the whole run
    grows outward from the selection's own center rather than from
    whichever card happened to be leftmost, so cards separate somewhat
    symmetrically rather than shooting off in one direction from a
    single anchor. Fewer than 2 cards has nothing to distribute, so
    every card's position is returned unchanged."""
    if len(cards) < 2:
        return {card.id: (card.x, card.y) for card in cards}
    width, _height = DEFAULT_CARD_SIZE
    ordered = sorted(cards, key=lambda card: card.x)
    left_x, right_x = ordered[0].x, ordered[-1].x
    natural_step = (right_x - left_x) / (len(ordered) - 1)
    min_step = width + TILE_GUTTER
    step = max(natural_step, min_step)
    if step > natural_step:
        center_x = (left_x + right_x) / 2
        start_x = center_x - step * (len(ordered) - 1) / 2
    else:
        start_x = left_x
    return {card.id: (start_x + i * step, card.y) for i, card in enumerate(ordered)}


def distribute_vertical(cards: list[Card]) -> dict[str, tuple[float, float]]:
    """Evenly spaces every card's y between the topmost and bottommost
    card's own y, leaving x untouched -- see distribute_horizontal for
    the full reasoning, including the minimum-spacing/grow-from-center
    behavior when the selection's own spread is too tight (or zero)."""
    if len(cards) < 2:
        return {card.id: (card.x, card.y) for card in cards}
    _width, height = DEFAULT_CARD_SIZE
    ordered = sorted(cards, key=lambda card: card.y)
    top_y, bottom_y = ordered[0].y, ordered[-1].y
    natural_step = (bottom_y - top_y) / (len(ordered) - 1)
    min_step = height + TILE_GUTTER
    step = max(natural_step, min_step)
    if step > natural_step:
        center_y = (top_y + bottom_y) / 2
        start_y = center_y - step * (len(ordered) - 1) / 2
    else:
        start_y = top_y
    return {card.id: (card.x, start_y + i * step) for i, card in enumerate(ordered)}
