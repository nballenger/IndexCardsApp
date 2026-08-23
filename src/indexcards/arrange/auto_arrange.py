from __future__ import annotations

import math
import random

from indexcards.models.card import DEFAULT_CARD_SIZE, Card

STACK_SPACING_X = 260.0
CASCADE_OFFSET = 24.0
TILE_GUTTER = 24.0
SCATTER_MAX_OVERLAP_FRACTION = 0.10
SCATTER_MAX_NEIGHBOR_DISTANCE = 2 * DEFAULT_CARD_SIZE[0]  # "two card lengths" — the long edge
SCATTER_MAX_ATTEMPTS_PER_CARD = 20


def _cascade_positions(cards: list[Card], origin_x: float) -> dict[str, tuple[float, float]]:
    return {
        card.id: (origin_x + CASCADE_OFFSET * i, CASCADE_OFFSET * i)
        for i, card in enumerate(cards)
    }


def arrange_by_color(cards: list[Card]) -> dict[str, tuple[float, float]]:
    """One stack per distinct color present, ordered by hex value for stable output."""
    groups: dict[str, list[Card]] = {}
    for card in cards:
        groups.setdefault(card.color, []).append(card)

    positions: dict[str, tuple[float, float]] = {}
    for i, color in enumerate(sorted(groups)):
        positions.update(_cascade_positions(groups[color], i * STACK_SPACING_X))
    return positions


def arrange_by_tag(cards: list[Card], tag: str) -> dict[str, tuple[float, float]]:
    """Two stacks: cards that have `tag`, and cards that don't."""
    has_tag = [card for card in cards if tag in card.tags]
    no_tag = [card for card in cards if tag not in card.tags]

    positions: dict[str, tuple[float, float]] = {}
    positions.update(_cascade_positions(has_tag, 0.0))
    positions.update(_cascade_positions(no_tag, STACK_SPACING_X))
    return positions


def arrange_by_tile(cards: list[Card], aspect_ratio: float = 1.0) -> dict[str, tuple[float, float]]:
    """Lays cards out in a row/column grid (order not significant), with a
    small gutter between cells. The number of columns is chosen so the
    overall grid's own width:height roughly matches aspect_ratio (e.g. a
    wide viewport gets a wide, short grid rather than a tall, narrow one)."""
    if not cards:
        return {}
    width, height = DEFAULT_CARD_SIZE
    columns = max(1, round(math.sqrt(len(cards) * aspect_ratio)))
    positions: dict[str, tuple[float, float]] = {}
    for i, card in enumerate(cards):
        row, column = divmod(i, columns)
        positions[card.id] = (
            column * (width + TILE_GUTTER),
            row * (height + TILE_GUTTER),
        )
    return positions


def _overlap_area(
    pos_a: tuple[float, float], pos_b: tuple[float, float], width: float, height: float
) -> float:
    ax, ay = pos_a
    bx, by = pos_b
    overlap_x = max(0.0, min(ax + width, bx + width) - max(ax, bx))
    overlap_y = max(0.0, min(ay + height, by + height) - max(ay, by))
    return overlap_x * overlap_y


def _max_overlap_fraction(
    candidate: tuple[float, float],
    placed: list[tuple[float, float]],
    width: float,
    height: float,
) -> float:
    card_area = width * height
    return max(
        (_overlap_area(candidate, other, width, height) / card_area for other in placed),
        default=0.0,
    )


def arrange_by_scatter(
    cards: list[Card], rng: random.Random | None = None
) -> dict[str, tuple[float, float]]:
    """Randomly scatters cards so they cluster loosely around each other
    rather than overlapping heavily or spreading out arbitrarily far:
    the first card is placed at the origin (the view is centered/panned
    onto the result afterward, same as every other arrange mode); each
    later card picks a random already-placed card as an anchor and tries
    up to SCATTER_MAX_ATTEMPTS_PER_CARD random points within
    SCATTER_MAX_NEIGHBOR_DISTANCE of it, accepting the first one that
    overlaps no already-placed card by more than
    SCATTER_MAX_OVERLAP_FRACTION of its area. If none of those attempts
    qualifies, it falls back to whichever candidate overlapped the least,
    so placement always terminates rather than retrying forever."""
    if not cards:
        return {}
    if rng is None:
        rng = random.Random()

    width, height = DEFAULT_CARD_SIZE
    positions: dict[str, tuple[float, float]] = {cards[0].id: (0.0, 0.0)}
    placed = [(0.0, 0.0)]

    for card in cards[1:]:
        anchor = rng.choice(placed)
        best_candidate = None
        best_overlap = math.inf
        for _attempt in range(SCATTER_MAX_ATTEMPTS_PER_CARD):
            angle = rng.uniform(0.0, 2 * math.pi)
            distance = rng.uniform(0.0, SCATTER_MAX_NEIGHBOR_DISTANCE)
            candidate = (
                anchor[0] + distance * math.cos(angle),
                anchor[1] + distance * math.sin(angle),
            )
            overlap = _max_overlap_fraction(candidate, placed, width, height)
            if overlap < best_overlap:
                best_candidate, best_overlap = candidate, overlap
            if overlap <= SCATTER_MAX_OVERLAP_FRACTION:
                break

        positions[card.id] = best_candidate
        placed.append(best_candidate)

    return positions


def auto_arrange_positions(
    cards: list[Card], group_by: str, tag: str | None = None, aspect_ratio: float = 1.0
) -> dict[str, tuple[float, float]]:
    if group_by == "color":
        return arrange_by_color(cards)
    if group_by == "tag":
        if not tag:
            raise ValueError("tag is required when group_by='tag'")
        return arrange_by_tag(cards, tag)
    if group_by == "tile":
        return arrange_by_tile(cards, aspect_ratio)
    if group_by == "scatter":
        return arrange_by_scatter(cards)
    raise ValueError(f"unknown group_by: {group_by!r}")
