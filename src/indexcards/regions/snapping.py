from __future__ import annotations

from collections.abc import Callable, Iterable

from indexcards.models.card import DEFAULT_CARD_SIZE
from indexcards.models.region import LABEL_BAR_HEIGHT, PLACEMENT_GUTTER, Region
from indexcards.regions.geometry import (
    Rect,
    contains_point,
    interior_rect,
    intersect,
    rect_center,
    to_rect,
    translate_to_separate,
)
from indexcards.regions.growth import resolve_region_growth

_MAX_ITERATIONS = 8
_MAX_ROUNDS = 4
_SETTLE_ROUNDS = 4

# Given a hypothetical region set, the overlap-label chip rects it would show
# (CanvasScene.overlap_label_rects_for); a drop that grows regions has to be
# checked against the chips of the GROWN set, not the current one.
LabelRectsFor = Callable[[list[Region]], list[Rect]]


def _no_labels(_regions: list[Region]) -> list[Rect]:
    return []


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


def _with_geometries(regions: list[Region], geometries: dict[str, Rect]) -> list[Region]:
    result = []
    for region in regions:
        x, y, width, height = geometries.get(region.id, to_rect(region))
        result.append(
            Region(id=region.id, x=x, y=y, width=width, height=height, label=region.label)
        )
    return result


def _enclose(region_rect: Rect, placed: Rect) -> Rect:
    """The smallest growth of region_rect that holds `placed` with the same
    placement insets interior_rect applies (gutter on the sides/bottom,
    label bar plus gutter on top)."""
    rx, ry, rw, rh = region_rect
    px, py, pw, ph = placed
    top_inset = LABEL_BAR_HEIGHT + PLACEMENT_GUTTER
    left = min(rx, px - PLACEMENT_GUTTER)
    top = min(ry, py - top_inset)
    right = max(rx + rw, px + pw + PLACEMENT_GUTTER)
    bottom = max(ry + rh, py + ph + PLACEMENT_GUTTER)
    return (left, top, right - left, bottom - top)


def resolve_drop_with_growth(
    rect: Rect,
    regions: Iterable[Region],
    label_rects_for: LabelRectsFor = _no_labels,
    max_iterations: int = _MAX_ITERATIONS,
) -> tuple[tuple[float, float], dict[str, Rect]] | None:
    """Like resolve_drop_against_regions_and_labels, but a region whose
    remaining free area is too small to hold rect (e.g. the sliver of
    region A not covered by an overlapping region B) grows to hold it
    instead of the drop failing. Returns ((dx, dy), {region_id: new_rect})
    -- the dict is empty when no growth was needed -- or None if there's no
    position even with growth (the caller should revert the drop).

    The item is placed by its center, as for any drop: pushed clear of
    every region its center ISN'T in (and of overlap chips), then each
    region its center IS in is grown just enough to enclose it, then the
    usual moat/overlap invariants are restored for whatever grew."""
    region_list = list(regions)
    delta = resolve_drop_against_regions_and_labels(
        rect, region_list, label_rects_for(region_list), max_iterations=max_iterations
    )
    if delta is not None:
        return delta, {}

    center = rect_center(rect)
    inside = [region for region in region_list if contains_point(to_rect(region), center)]
    if not inside:
        return None
    inside_ids = {region.id for region in inside}
    avoid = [to_rect(region) for region in region_list if region.id not in inside_ids]
    push = resolve_drop_against_obstacles(
        rect, avoid + label_rects_for(region_list), max_iterations=max_iterations
    )
    if push is None:
        return None
    x, y, width, height = rect
    placed = (x + push[0], y + push[1], width, height)

    original = {region.id: to_rect(region) for region in region_list}
    current = dict(original)
    for region in sorted(inside, key=lambda r: r.width * r.height):
        current[region.id] = _enclose(current[region.id], placed)
        diff = resolve_region_growth(
            region.id, current[region.id], _with_geometries(region_list, current)
        )
        if diff is None:
            return None
        current.update(diff)

    final_regions = _with_geometries(region_list, current)
    final = resolve_drop_against_regions_and_labels(
        placed, final_regions, label_rects_for(final_regions), max_iterations=max_iterations
    )
    if final is None:
        return None
    grown = {rid: geometry for rid, geometry in current.items() if geometry != original[rid]}
    return (push[0] + final[0], push[1] + final[1]), grown


def settle_items_against_regions(
    positions: dict[str, tuple[float, float]],
    regions: Iterable[Region],
    label_rects_for: LabelRectsFor = _no_labels,
    max_iterations: int = 50,
    blockers: dict[str, tuple[float, float]] | None = None,
) -> tuple[dict[str, tuple[float, float]], dict[str, Rect]]:
    """For card-footprint-sized items (cards, stacks) at `positions`,
    returns (moved, grown): the new position of every item that has to
    move so it sits fully inside or fully outside every region (and clear
    of overlap-label chips) -- exactly what a drop does for a single item,
    applied after the REGIONS changed instead -- and the new rect of every
    region that had to grow to hold an item whose free area was too small
    (see resolve_drop_with_growth). Each item is resolved by its own
    center, so an item whose center is in an overlap ends up inside both
    regions' interiors. Growth can swallow a neighbor that was already
    settled, so this repeats until nothing changes (a few rounds at most).

    An item that has to move is also nudged clear of every other item
    (`positions` plus `blockers`, e.g. the other kind of item) so settling
    doesn't pile things on top of each other; if that can't be satisfied
    together with the region rules, the region rules win. An item that
    doesn't need to move is never touched, and one that can't be resolved
    at all is left where it is rather than failing the whole gesture."""
    region_list = list(regions)
    original = {region.id: to_rect(region) for region in region_list}
    geometries = dict(original)
    width, height = DEFAULT_CARD_SIZE
    current = dict(positions)
    others = dict(blockers or {})
    for _ in range(_SETTLE_ROUNDS):
        changed = False
        for item_id in positions:
            x, y = current[item_id]
            rect = (x, y, width, height)
            live = _with_geometries(region_list, geometries)
            resolution = resolve_drop_with_growth(
                rect, live, label_rects_for, max_iterations=max_iterations
            )
            if resolution is None:
                continue
            delta, grown = resolution
            if not grown and delta == (0.0, 0.0):
                continue
            if grown:
                geometries.update(grown)
                live = _with_geometries(region_list, geometries)
            neighbor_rects = [
                (nx, ny, width, height)
                for other_id, (nx, ny) in {**others, **current}.items()
                if other_id != item_id
            ]
            clear = resolve_drop_against_regions_and_labels(
                rect,
                live,
                label_rects_for(live) + neighbor_rects,
                max_rounds=12,
                max_iterations=max_iterations,
            )
            if clear is not None:
                delta = clear
            current[item_id] = (x + delta[0], y + delta[1])
            changed = True
        if not changed:
            break
    moved = {item_id: pos for item_id, pos in current.items() if pos != positions[item_id]}
    grown_total = {rid: g for rid, g in geometries.items() if g != original[rid]}
    return moved, grown_total
