from __future__ import annotations

from collections.abc import Iterable

from indexcards.models.region import Region
from indexcards.regions.geometry import (
    Rect,
    contains_point,
    rect_center,
    to_rect,
    translate_to_separate,
)

_MAX_ITERATIONS = 8


def _overlap(a: Rect, b: Rect) -> tuple[float, float]:
    """(overlap_x, overlap_y) -- positive where a and b intersect on that
    axis, zero or negative where they don't."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    overlap_x = min(ax + aw, bx + bw) - max(ax, bx)
    overlap_y = min(ay + ah, by + bh) - max(ay, by)
    return overlap_x, overlap_y


def _straddles(rect: Rect, obstacle: Rect) -> bool:
    overlap_x, overlap_y = _overlap(rect, obstacle)
    if overlap_x <= 0 or overlap_y <= 0:
        return False  # fully disjoint on at least one axis
    x, y, width, height = rect
    ox, oy, ow, oh = obstacle
    fully_contained = ox <= x and x + width <= ox + ow and oy <= y and y + height <= oy + oh
    return not fully_contained


def _translate_to_contain(rect: Rect, outer: Rect) -> tuple[float, float] | None:
    x, y, width, height = rect
    ox, oy, ow, oh = outer
    if width > ow or height > oh:
        return None  # can never fit inside outer by translation alone
    dx = 0.0
    if x < ox:
        dx = ox - x
    elif x + width > ox + ow:
        dx = (ox + ow) - (x + width)
    dy = 0.0
    if y < oy:
        dy = oy - y
    elif y + height > oy + oh:
        dy = (oy + oh) - (y + height)
    return dx, dy


def resolve_drop_against_regions(
    rect: Rect, regions: Iterable[Region], max_iterations: int = _MAX_ITERATIONS
) -> tuple[float, float] | None:
    """(dx, dy) to translate rect so it doesn't straddle any region's
    border, or None if no such translation was found within
    max_iterations (the caller should revert the drop). Each region's
    desired side (in/out) is decided once, from rect's ORIGINAL center,
    and held fixed through every iteration -- it never flip-flops."""
    region_list = sorted(regions, key=lambda region: region.width * region.height)
    region_rects = {region.id: to_rect(region) for region in region_list}
    original_center = rect_center(rect)
    desired_inside = {
        region.id: contains_point(region_rects[region.id], original_center)
        for region in region_list
    }

    x, y, width, height = rect
    total_dx = total_dy = 0.0

    for _ in range(max_iterations):
        current = (x + total_dx, y + total_dy, width, height)
        violated = next(
            (region for region in region_list if _straddles(current, region_rects[region.id])),
            None,
        )
        if violated is None:
            return total_dx, total_dy

        obstacle = region_rects[violated.id]
        if desired_inside[violated.id]:
            delta = _translate_to_contain(current, obstacle)
            if delta is None:
                return None
        else:
            delta = translate_to_separate(current, obstacle)
        total_dx += delta[0]
        total_dy += delta[1]

    return None
