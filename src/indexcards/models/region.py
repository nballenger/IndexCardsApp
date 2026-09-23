from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from indexcards.models.card import DEFAULT_CARD_SIZE

# Public (no leading underscore): canvas/region_item.py's rendering and
# regions/geometry.py's placement math both need these, and models/ can't
# depend on canvas/, so they live here as the shared source of truth.
LABEL_BAR_HEIGHT = 28.0
CORNER_RADIUS = 14.0
PLACEMENT_GUTTER = 16.0  # > CORNER_RADIUS -- clears the rounded corners with room to spare

# Two distinct "room for a card" minimums, previously conflated as one:
# a region's own footprint needs its label bar (top, a hard edge) PLUS
# gutter (sides/bottom, clearing the rounded corners); a generic empty
# area with no label bar of its own (a moat strip, an overlap sliver)
# just needs gutter on all four sides.
MIN_REGION_SIZE = (
    DEFAULT_CARD_SIZE[0] + 2 * PLACEMENT_GUTTER,
    DEFAULT_CARD_SIZE[1] + LABEL_BAR_HEIGHT + PLACEMENT_GUTTER,
)
CARD_CLEARANCE_SIZE = (
    DEFAULT_CARD_SIZE[0] + 2 * PLACEMENT_GUTTER,
    DEFAULT_CARD_SIZE[1] + 2 * PLACEMENT_GUTTER,
)
DEFAULT_REGION_SIZE = (360.0, 220.0)


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class Region:
    id: str
    x: float = 0.0
    y: float = 0.0
    width: float = DEFAULT_REGION_SIZE[0]
    height: float = DEFAULT_REGION_SIZE[1]
    label: str = ""
    created_at: str = field(default_factory=_now)
    modified_at: str = field(default_factory=_now)
