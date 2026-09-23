from __future__ import annotations

from indexcards.models.card import DEFAULT_CARD_SIZE, Card
from indexcards.models.region import (
    CARD_CLEARANCE_SIZE,
    LABEL_BAR_HEIGHT,
    MIN_REGION_SIZE,
    PLACEMENT_GUTTER,
    Region,
)
from indexcards.models.stack import Stack

Rect = tuple[float, float, float, float]  # x, y, width, height

_PADDING = 24.0


def to_rect(region: Region) -> Rect:
    return (region.x, region.y, region.width, region.height)


def rect_center(rect: Rect) -> tuple[float, float]:
    x, y, width, height = rect
    return (x + width / 2, y + height / 2)


def contains_point(rect: Rect, point: tuple[float, float]) -> bool:
    x, y, width, height = rect
    px, py = point
    return x <= px <= x + width and y <= py <= y + height


def intersect(a: Rect, b: Rect) -> Rect | None:
    """The overlap rectangle of a and b, or None if they don't overlap --
    touching edges count as no overlap."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    left, top = max(ax, bx), max(ay, by)
    right, bottom = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    if right <= left or bottom <= top:
        return None
    return (left, top, right - left, bottom - top)


def margin_strips(outer: Rect, obstacle: Rect) -> list[Rect]:
    """Up to 4 candidate rects covering outer's area not covered by
    obstacle (obstacle is clipped to outer first via intersect, so this
    works whether obstacle sits wholly inside outer -- a nesting "moat" --
    or only partially overlaps it -- an overlap "own-only face"). With a
    single obstacle this is a complete existence check for "is there room
    for a card somewhere in outer, outside obstacle": the largest empty
    rectangle around one hole is always anchored to one of outer's four
    edges, so these four strips are exhaustive. Degenerate (<=0 width or
    height) strips are omitted."""
    clipped = intersect(outer, obstacle)
    if clipped is None:
        return [outer]
    ox, oy, ow, oh = outer
    cx, cy, cw, ch = clipped
    strips = []
    left_width = cx - ox
    if left_width > 0:
        strips.append((ox, oy, left_width, oh))
    right_width = (ox + ow) - (cx + cw)
    if right_width > 0:
        strips.append((cx + cw, oy, right_width, oh))
    top_height = cy - oy
    if top_height > 0:
        strips.append((ox, oy, ow, top_height))
    bottom_height = (oy + oh) - (cy + ch)
    if bottom_height > 0:
        strips.append((ox, cy + ch, ow, bottom_height))
    return strips


def has_room_for_card(rect: Rect, min_size: tuple[float, float] = CARD_CLEARANCE_SIZE) -> bool:
    return rect[2] >= min_size[0] and rect[3] >= min_size[1]


def interior_rect(rect: Rect) -> Rect:
    """The usable placement area inside a region's rect -- inset by
    PLACEMENT_GUTTER on the left/right/bottom (clears the rounded
    corners) and by LABEL_BAR_HEIGHT on top (a hard edge, no extra
    gutter needed below it). A card is only genuinely "fully inside" a
    region if it fits within this, not the region's own raw rect --
    membership (contained_card_ids/_contains) is unaffected and still
    uses the raw rect's center-point containment; this only changes
    where a card/stack is allowed to actually rest."""
    x, y, width, height = rect
    return (
        x + PLACEMENT_GUTTER,
        y + LABEL_BAR_HEIGHT,
        width - 2 * PLACEMENT_GUTTER,
        height - LABEL_BAR_HEIGHT - PLACEMENT_GUTTER,
    )


def translate_to_separate(rect: Rect, obstacle: Rect) -> tuple[float, float]:
    """Minimal (dx, dy) pushing rect fully clear of obstacle -- standard
    AABB minimum-translation-vector: push along whichever axis has the
    smaller overlap depth, away from obstacle's center. (0, 0) if they
    don't overlap at all."""
    overlap = intersect(rect, obstacle)
    if overlap is None:
        return (0.0, 0.0)
    _, _, overlap_width, overlap_height = overlap
    rect_cx, rect_cy = rect_center(rect)
    obstacle_cx, obstacle_cy = rect_center(obstacle)
    if overlap_width <= overlap_height:
        direction = -1.0 if rect_cx < obstacle_cx else 1.0
        return direction * overlap_width, 0.0
    direction = -1.0 if rect_cy < obstacle_cy else 1.0
    return 0.0, direction * overlap_height


def _contains(region: Region, point: tuple[float, float]) -> bool:
    return contains_point(to_rect(region), point)


def _card_center(card: Card) -> tuple[float, float]:
    width, height = DEFAULT_CARD_SIZE
    return (card.x + width / 2, card.y + height / 2)


def _stack_center(stack: Stack) -> tuple[float, float]:
    width, height = DEFAULT_CARD_SIZE
    return (stack.x + width / 2, stack.y + height / 2)


def contained_card_ids(region: Region, cards) -> list[str]:
    """Loose cards (stack_id is None) whose center falls within region's
    rectangle -- membership is derived, never stored. A stacked card rides
    with its Stack instead, since it has no position of its own."""
    return [
        card.id for card in cards if card.stack_id is None and _contains(region, _card_center(card))
    ]


def contained_stack_ids(region: Region, stacks) -> list[str]:
    return [stack.id for stack in stacks if _contains(region, _stack_center(stack))]


def cards_in_any_region(cards, regions) -> set[str]:
    """Ids of loose cards whose center falls inside at least one region --
    used by auto-arrange to treat region membership like the pinned flag."""
    regions = list(regions)
    ids: set[str] = set()
    for region in regions:
        ids.update(contained_card_ids(region, cards))
    return ids


def stacks_in_any_region(stacks, regions) -> set[str]:
    regions = list(regions)
    ids: set[str] = set()
    for region in regions:
        ids.update(contained_stack_ids(region, stacks))
    return ids


def to_corner_bbox(rect: Rect) -> tuple[float, float, float, float]:
    """(x, y, w, h) -> (x1, y1, x2, y2) -- converts from this module's Rect
    convention to arrange/auto_arrange.py's own two-corner bbox convention
    (positions_bbox/union_bbox), which assumes card-footprint-sized
    obstacles and can't represent an arbitrary-sized region directly."""
    x, y, width, height = rect
    return (x, y, x + width, y + height)


def bounds_for(cards, stacks, padding: float = _PADDING, label_bar: float = LABEL_BAR_HEIGHT):
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
