from __future__ import annotations

import random

from indexcards.arrange.auto_arrange import (
    STACK_EXPLODE_GUTTER,
    arrange_by_scatter,
    arrange_by_tile,
    shift_layout_to_clear,
)
from indexcards.models.card import Card
from indexcards.models.stack import Stack


def compute_explode_layout(
    stack: Stack,
    member_cards: list[Card],
    group_by: str,
    other_card_positions: dict[str, tuple[float, float]],
    other_stack_positions: dict[str, tuple[float, float]],
    aspect_ratio: float = 1.0,
    rng: random.Random | None = None,
) -> dict[str, tuple[float, float]]:
    """Lays out a stack's member cards (tiled or scattered, per group_by),
    anchored at the stack's own canvas position, then shifted just far
    enough to clear every other card and stack currently on the canvas —
    "an unoccupied section of the canvas," reusing the same
    shift-to-clear-overlap technique auto-arrange uses to avoid pinned
    cards. Merging card-id-keyed and stack-id-keyed position dicts into
    one obstacle dict is safe since those ids use distinct prefixes
    (c_/s_)."""
    arrange_fn = arrange_by_tile if group_by == "tile" else arrange_by_scatter
    raw = arrange_fn(member_cards, aspect_ratio, rng)
    anchored = {card_id: (x + stack.x, y + stack.y) for card_id, (x, y) in raw.items()}
    obstacles = {**other_card_positions, **other_stack_positions}
    return shift_layout_to_clear(anchored, obstacles, STACK_EXPLODE_GUTTER)
