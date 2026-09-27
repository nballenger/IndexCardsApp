from __future__ import annotations

from collections.abc import Iterable

from indexcards.models.card import DEFAULT_CARD_SIZE
from indexcards.models.region import Region
from indexcards.regions.geometry import (
    Rect,
    contains_point,
    interior_rect,
    intersect,
    rect_center,
    to_rect,
    translate_to_separate,
)

_MAX_ITERATIONS = 8
_MAX_ROUNDS = 4


def _overlap(a: Rect, b: Rect) -> tuple[float, float]:
    """(overlap_x, overlap_y) -- positive where a and b intersect on that
    axis, zero or negative where they don't."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    overlap_x = min(ax + aw, bx + bw) - max(ax, bx)
    overlap_y = min(ay + ah, by + bh) - max(ay, by)
    return overlap_x, overlap_y


def _fully_contains(outer: Rect, rect: Rect) -> bool:
    x, y, width, height = rect
    ox, oy, ow, oh = outer
    return ox <= x and x + width <= ox + ow and oy <= y and y + height <= oy + oh


def _straddles(rect: Rect, obstacle: Rect) -> bool:
    """True if rect overlaps obstacle's raw rect at all but isn't fully
    inside obstacle's INTERIOR (the placement-safe area, inset for the
    rounded corners and label bar -- see geometry.interior_rect). A card
    fully clear of the raw rect needs no such margin: the rounded corner
    only recedes inward, it never bulges outward, so exterior
    flush-adjacency is never visually broken."""
    overlap_x, overlap_y = _overlap(rect, obstacle)
    if overlap_x <= 0 or overlap_y <= 0:
        return False  # fully clear of the region entirely
    return not _fully_contains(interior_rect(obstacle), rect)


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
            delta = _translate_to_contain(current, interior_rect(obstacle))
            if delta is None:
                return None
        else:
            delta = translate_to_separate(current, obstacle)
        total_dx += delta[0]
        total_dy += delta[1]

    return None


def resolve_drop_against_obstacles(
    rect: Rect, obstacles: Iterable[Rect], max_iterations: int = _MAX_ITERATIONS
) -> tuple[float, float] | None:
    """Like resolve_drop_against_regions, but for plain rects with no
    inside/outside concept at all -- always push clear, regardless of
    where rect's center landed. Used for overlap-label chips, which a
    card must never sit on."""
    obstacle_list = list(obstacles)
    x, y, width, height = rect
    total_dx = total_dy = 0.0

    for _ in range(max_iterations):
        current = (x + total_dx, y + total_dy, width, height)
        violated = next((o for o in obstacle_list if intersect(current, o) is not None), None)
        if violated is None:
            return total_dx, total_dy
        dx, dy = translate_to_separate(current, violated)
        total_dx += dx
        total_dy += dy

    return None


def resolve_drop_against_regions_and_labels(
    rect: Rect,
    regions: Iterable[Region],
    label_rects: Iterable[Rect] = (),
    max_rounds: int = _MAX_ROUNDS,
    max_iterations: int = _MAX_ITERATIONS,
) -> tuple[float, float] | None:
    """Combines resolve_drop_against_regions (region borders) with
    resolve_drop_against_obstacles (overlap-label chips), alternating up
    to max_rounds times in case fixing one reintroduces the other -- rare
    in practice, since a label chip always sits inside a region's own
    interior, nowhere near where the region-boundary fix would push a
    card in the first place."""
    regions = list(regions)
    label_rects = list(label_rects)
    x, y, width, height = rect
    total_dx = total_dy = 0.0

    for _ in range(max_rounds):
        current = (x + total_dx, y + total_dy, width, height)
        region_delta = resolve_drop_against_regions(current, regions, max_iterations)
        if region_delta is None:
            return None
        total_dx += region_delta[0]
        total_dy += region_delta[1]

        current = (x + total_dx, y + total_dy, width, height)
        label_delta = resolve_drop_against_obstacles(current, label_rects)
        if label_delta is None:
            return None
        total_dx += label_delta[0]
        total_dy += label_delta[1]

        if region_delta == (0.0, 0.0) and label_delta == (0.0, 0.0):
            return total_dx, total_dy

    return None


def settle_items_against_regions(
    positions: dict[str, tuple[float, float]],
    regions: Iterable[Region],
    label_rects: Iterable[Rect] = (),
    max_iterations: int = 50,
    blockers: dict[str, tuple[float, float]] | None = None,
) -> dict[str, tuple[float, float]]:
    """For card-footprint-sized items (cards, stacks) at `positions`, the new
    position of every one that has to move so it sits fully inside or fully
    outside every region (and clear of overlap-label chips) -- exactly what
    a drop does for a single item, applied after the REGIONS changed
    instead (a region was created, dragged, or resized over things that
    were already there). Each item is resolved independently, by its own
    center, so an item whose center is in an overlap ends up inside both
    regions' interiors.

    An item that has to move is also nudged clear of every other item
    (`positions` plus `blockers`, e.g. the other kind of item) so settling
    doesn't pile things on top of each other; if that can't be satisfied
    together with the region rules, the region rules win. An item that
    doesn't need to move is never touched, and one that can't be resolved
    at all is left where it is rather than failing the whole gesture."""
    region_list = list(regions)
    label_list = list(label_rects)
    width, height = DEFAULT_CARD_SIZE
    current = dict(positions)
    others = dict(blockers or {})
    moved: dict[str, tuple[float, float]] = {}
    for item_id, (x, y) in positions.items():
        rect = (x, y, width, height)
        delta = resolve_drop_against_regions_and_labels(
            rect, region_list, label_list, max_iterations=max_iterations
        )
        if delta is None or delta == (0.0, 0.0):
            continue
        neighbor_rects = [
            (nx, ny, width, height)
            for other_id, (nx, ny) in {**others, **current}.items()
            if other_id != item_id
        ]
        clear = resolve_drop_against_regions_and_labels(
            rect,
            region_list,
            label_list + neighbor_rects,
            max_rounds=12,
            max_iterations=max_iterations,
        )
        if clear is not None:
            delta = clear
        current[item_id] = (x + delta[0], y + delta[1])
        moved[item_id] = current[item_id]
    return moved
