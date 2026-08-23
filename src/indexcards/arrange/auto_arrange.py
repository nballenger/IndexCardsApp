from __future__ import annotations

import math

from indexcards.models.card import DEFAULT_CARD_SIZE, Card

STACK_SPACING_X = 260.0
CASCADE_OFFSET = 24.0
TILE_GUTTER = 24.0


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
    raise ValueError(f"unknown group_by: {group_by!r}")
