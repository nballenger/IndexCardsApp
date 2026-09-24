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
# Every region sits below cards/stacks/links (z >= 1); among regions, a
# smaller (more likely nested) one sits above a larger one, via
# BASE_Z_VALUE - area / 1_000_000. An overlap-label chip between two
# regions uses the same formula (smaller area wins) plus a small offset,
# so it always sits above whichever of its two regions would otherwise be
# on top -- still far below cards.
BASE_Z_VALUE = -1000.0

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

# The footprint reserved for an auto-generated "Alpha and Bravo" overlap
# label -- comfortably smaller than CARD_CLEARANCE_SIZE, so it always fits
# inside any overlap face the growth invariant already guarantees room
# for. The rendered chip's text is elided to this same width, so the
# exclusion zone and the visible chip never disagree.
OVERLAP_LABEL_SIZE = (200.0, 26.0)


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
