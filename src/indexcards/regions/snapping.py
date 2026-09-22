from __future__ import annotations

from collections.abc import Iterable

from indexcards.models.region import Region

Rect = tuple[float, float, float, float]  # x, y, width, height

_MAX_ITERATIONS = 8


def _center(rect: Rect) -> tuple[float, float]:
    x, y, width, height = rect
    return (x + width / 2, y + height / 2)


def _contains_point(region: Region, point: tuple[float, float]) -> bool:
    px, py = point
    return region.x <= px <= region.x + region.width and region.y <= py <= region.y + region.height


def _overlap(rect: Rect, region: Region) -> tuple[float, float]:
    """(overlap_x, overlap_y) -- positive where rect and region's rectangle
    intersect on that axis, zero or negative where they don't."""
    x, y, width, height = rect
    overlap_x = min(x + width, region.x + region.width) - max(x, region.x)
    overlap_y = min(y + height, region.y + region.height) - max(y, region.y)
    return overlap_x, overlap_y


def _straddles(rect: Rect, region: Region) -> bool:
    overlap_x, overlap_y = _overlap(rect, region)
    if overlap_x <= 0 or overlap_y <= 0:
        return False  # fully disjoint on at least one axis
    x, y, width, height = rect
    fully_contained = (
        region.x <= x
        and x + width <= region.x + region.width
        and region.y <= y
        and y + height <= region.y + region.height
    )
    return not fully_contained


def _translate_to_contain(rect: Rect, region: Region) -> tuple[float, float] | None:
    x, y, width, height = rect
    if width > region.width or height > region.height:
        return None  # can never fit inside this region by translation alone
    dx = 0.0
    if x < region.x:
        dx = region.x - x
    elif x + width > region.x + region.width:
        dx = (region.x + region.width) - (x + width)
    dy = 0.0
    if y < region.y:
        dy = region.y - y
    elif y + height > region.y + region.height:
        dy = (region.y + region.height) - (y + height)
    return dx, dy


def _translate_to_separate(rect: Rect, region: Region) -> tuple[float, float]:
    overlap_x, overlap_y = _overlap(rect, region)
    rect_cx, rect_cy = _center(rect)
    region_cx, region_cy = region.x + region.width / 2, region.y + region.height / 2
    if overlap_x <= overlap_y:
        direction = -1.0 if rect_cx < region_cx else 1.0
        return direction * overlap_x, 0.0
    direction = -1.0 if rect_cy < region_cy else 1.0
    return 0.0, direction * overlap_y


def resolve_drop_against_regions(
    rect: Rect, regions: Iterable[Region], max_iterations: int = _MAX_ITERATIONS
) -> tuple[float, float] | None:
    """(dx, dy) to translate rect so it doesn't straddle any region's
    border, or None if no such translation was found within
    max_iterations (the caller should revert the drop). Each region's
    desired side (in/out) is decided once, from rect's ORIGINAL center,
    and held fixed through every iteration -- it never flip-flops."""
    regions = sorted(regions, key=lambda region: region.width * region.height)
    original_center = _center(rect)
    desired_inside = {region.id: _contains_point(region, original_center) for region in regions}

    x, y, width, height = rect
    total_dx = total_dy = 0.0

    for _ in range(max_iterations):
        current = (x + total_dx, y + total_dy, width, height)
        violated = next((region for region in regions if _straddles(current, region)), None)
        if violated is None:
            return total_dx, total_dy

        if desired_inside[violated.id]:
            delta = _translate_to_contain(current, violated)
            if delta is None:
                return None
        else:
            delta = _translate_to_separate(current, violated)
        total_dx += delta[0]
        total_dy += delta[1]

    return None
