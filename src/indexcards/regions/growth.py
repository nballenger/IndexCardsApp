from __future__ import annotations

from collections.abc import Iterable

from indexcards.models.region import CARD_CLEARANCE_SIZE, MIN_REGION_SIZE, Region
from indexcards.regions.geometry import (
    Rect,
    has_room_for_card,
    intersect,
    margin_strips,
    relationship,
    to_rect,
)

_MAX_ITERATIONS = 12
# Repair (load-time, no gesture) can afford far more iterations than a
# live drag -- it runs once on open, not per mouse-move -- and stage 2b's
# own finding was that even an adversarial dense cluster converges by ~50.
_REPAIR_MAX_ITERATIONS = 200
# Fixed tie-break order for "which edge grows" when more than one edge
# needs the same amount of growth -- arbitrary but deterministic.
_EDGE_ORDER = ("left", "right", "top", "bottom")


def _room_available(outer: Rect, obstacle: Rect, min_size: tuple[float, float]) -> bool:
    return any(has_room_for_card(strip, min_size) for strip in margin_strips(outer, obstacle))


def _grow_by_edge(outer: Rect, edge: str, deficit: float) -> Rect:
    x, y, width, height = outer
    if edge == "left":
        return (x - deficit, y, width + deficit, height)
    if edge == "right":
        return (x, y, width + deficit, height)
    if edge == "top":
        return (x, y - deficit, width, height + deficit)
    return (x, y, width, height + deficit)  # bottom


def _deficits_for_room(
    outer: Rect, obstacle: Rect, min_size: tuple[float, float]
) -> dict[str, float]:
    """How much outer would need to grow, per edge, for AT LEAST ONE
    margin strip on that edge to satisfy min_size -- only the edges whose
    strip is the deficient dimension are meaningful (growing the left/right
    edge only ever helps a strip's width; top/bottom only ever helps a
    strip's height), so this checks each edge against the strip it would
    actually extend."""
    ox, oy, ow, oh = outer
    clipped = intersect(outer, obstacle)
    if clipped is None:
        return {}  # already has full room (outer itself, per margin_strips)
    cx, cy, cw, ch = clipped
    min_w, min_h = min_size

    deficits: dict[str, float] = {}
    left_w = cx - ox
    if oh >= min_h and left_w < min_w:
        deficits["left"] = min_w - left_w
    right_w = (ox + ow) - (cx + cw)
    if oh >= min_h and right_w < min_w:
        deficits["right"] = min_w - right_w
    top_h = cy - oy
    if ow >= min_w and top_h < min_h:
        deficits["top"] = min_h - top_h
    bottom_h = (oy + oh) - (cy + ch)
    if ow >= min_w and bottom_h < min_h:
        deficits["bottom"] = min_h - bottom_h
    return deficits


def grow_to_fit_obstacle(
    outer: Rect, obstacle: Rect, min_size: tuple[float, float] = CARD_CLEARANCE_SIZE
) -> Rect | None:
    """None if outer already has a margin_strips() candidate >= min_size.
    Otherwise the smallest single-edge extension of outer -- away from
    obstacle -- that opens one, trying left/right/top/bottom in that fixed
    order on ties."""
    if _room_available(outer, obstacle, min_size):
        return None
    deficits = _deficits_for_room(outer, obstacle, min_size)
    if not deficits:
        # Every caller passes an actual region as outer, which never
        # shrinks below MIN_REGION_SIZE -- itself always >= min_size here
        # (CARD_CLEARANCE_SIZE) -- which is exactly what makes at least
        # one edge's deficit computable above; this is a defensive
        # fallback for that invariant being violated, not an expected path.
        ox, oy, ow, oh = outer
        min_w, min_h = min_size
        return (ox, oy, ow + min_w, oh + min_h)
    best_edge = min(_EDGE_ORDER, key=lambda edge: deficits.get(edge, float("inf")))
    return _grow_by_edge(outer, best_edge, deficits[best_edge])


def grow_to_fit_intersection(
    outer: Rect, obstacle: Rect, min_size: tuple[float, float] = MIN_REGION_SIZE
) -> Rect | None:
    """None if intersect(outer, obstacle) already satisfies min_size (by
    default MIN_REGION_SIZE, not just a card's clearance: an overlap's top
    edge is always exactly one of the two regions' own top, so that
    region's title bar sits at the top of the overlap face and a card
    needs room below it too).
    Otherwise the smallest single-edge extension of outer INTO the shared
    axis (growing toward/through obstacle) that grows the overlap to
    min_size."""
    overlap = intersect(outer, obstacle)
    min_w, min_h = min_size
    if overlap is not None and has_room_for_card(overlap, min_size):
        return None

    ox, oy, ow, oh = outer
    bx, by, bw, bh = obstacle
    overlap_w = 0.0 if overlap is None else overlap[2]
    overlap_h = 0.0 if overlap is None else overlap[3]

    # Growing "into" obstacle along x means extending whichever of outer's
    # left/right edges is on the side obstacle doesn't already cover, up
    # to obstacle's own extent on that axis (can't grow past obstacle's
    # far edge and call it "intersection").
    candidates: dict[str, tuple[Rect, float]] = {}
    if overlap_w < min_w:
        deficit_w = min_w - overlap_w
        if ox <= bx:  # outer's right edge is the one that can grow rightward into obstacle
            new_right = min(ox + ow + deficit_w, bx + bw)
            grown_w = new_right - ox
            if grown_w > ow:
                candidates["right"] = ((ox, oy, grown_w, oh), grown_w - ow)
        else:  # outer's left edge grows leftward into obstacle
            new_left = max(ox - deficit_w, bx)
            grown_w = (ox + ow) - new_left
            if grown_w > ow:
                candidates["left"] = ((new_left, oy, grown_w, oh), (ox + ow) - new_left - ow)
    if overlap_h < min_h:
        deficit_h = min_h - overlap_h
        if oy <= by:
            new_bottom = min(oy + oh + deficit_h, by + bh)
            grown_h = new_bottom - oy
            if grown_h > oh:
                candidates["bottom"] = ((ox, oy, ow, grown_h), grown_h - oh)
        else:
            new_top = max(oy - deficit_h, by)
            grown_h = (oy + oh) - new_top
            if grown_h > oh:
                candidates["top"] = ((ox, new_top, ow, grown_h), (oy + oh) - new_top - oh)

    if not candidates:
        return None  # obstacle isn't big enough to grow "into" on either axis
    best_edge = min(
        (edge for edge in _EDGE_ORDER if edge in candidates), key=lambda edge: candidates[edge][1]
    )
    return candidates[best_edge][0]


def resolve_region_growth(
    changed_region_id: str,
    changed_geometry: Rect,
    regions: Iterable[Region],
    *,
    max_iterations: int = _MAX_ITERATIONS,
) -> dict[str, Rect] | None:
    """changed_region_id need not already exist in `regions` (the creation
    call sites pass an id that isn't in the document yet). Returns a
    {region_id: new_geometry} diff for every region that had to change --
    possibly including changed_region_id itself (it's acting as a
    container that now needs a bigger moat) -- or None if
    nothing converges within max_iterations, meaning the caller reverts
    the whole gesture."""
    current: dict[str, Rect] = {region.id: to_rect(region) for region in regions}
    current[changed_region_id] = changed_geometry
    touched: set[str] = set()

    for _ in range(max_iterations):
        ids = sorted(current, key=lambda region_id: current[region_id][2] * current[region_id][3])

        # 1) moat: any region whose fully-contained children (as one union
        # bbox) leave it without room for a card.
        fixed_a_violation = False
        for container_id in ids:
            child_ids = [
                other_id
                for other_id in ids
                if other_id != container_id
                and relationship(current[container_id], current[other_id]) == "a_contains_b"
            ]
            if not child_ids:
                continue
            children_union = _union(current[child_id] for child_id in child_ids)
            grown = grow_to_fit_obstacle(current[container_id], children_union)
            if grown is not None:
                current[container_id] = grown
                touched.add(container_id)
                fixed_a_violation = True
                break
        if fixed_a_violation:
            continue

        # 2) pairwise overlap (neither contains the other): the shared face.
        fixed_a_violation = False
        for i, id_a in enumerate(ids):
            for id_b in ids[i + 1 :]:
                if relationship(current[id_a], current[id_b]) != "overlap":
                    continue
                grower_id, obstacle_id = _overlap_violation(
                    id_a, current[id_a], id_b, current[id_b], changed_region_id
                )
                if grower_id is None:
                    continue
                fixed = grow_to_fit_intersection(current[grower_id], current[obstacle_id])
                if fixed is None:
                    continue
                current[grower_id] = fixed
                touched.add(grower_id)
                fixed_a_violation = True
                break
            if fixed_a_violation:
                break
        if fixed_a_violation:
            continue

        # Nothing left to fix.
        return {region_id: current[region_id] for region_id in touched}

    return None


def _union(rects: Iterable[Rect]) -> Rect:
    rects = list(rects)
    left = min(r[0] for r in rects)
    top = min(r[1] for r in rects)
    right = max(r[0] + r[2] for r in rects)
    bottom = max(r[1] + r[3] for r in rects)
    return (left, top, right - left, bottom - top)


def repair_region_geometry(
    regions: Iterable[Region], max_iterations: int = _REPAIR_MAX_ITERATIONS
) -> dict[str, Rect] | None:
    """Grows whichever regions are needed so every moat and pairwise-
    overlap invariant resolve_region_growth enforces live is already
    satisfied -- for a document loaded from disk, which never goes
    through a gesture. resolve_region_growth already scans and fixes
    violations across the WHOLE region set on every call (changed_region_id
    only affects which geometry gets substituted for one id up front, and
    tie-breaking for who grows on a shared-intersection violation that id
    is part of -- see _overlap_violation's own downstream-cascade
    fallback, which already handles every OTHER pair deterministically).
    So this needs no per-region outer loop: pick one region (the smallest
    id, an arbitrary but stable and reproducible choice) and substitute
    its own current geometry for itself -- a true no-op -- purely to
    satisfy the required parameter. Repair only ever grows, never
    repositions a region the file said was somewhere specific. Returns
    {} if there's nothing to fix (including 0 or 1 regions), a diff of
    what grew, or None if even this generous a
    budget couldn't converge -- the caller should report that rather
    than hang or silently leave something invalid."""
    region_list = list(regions)
    if len(region_list) < 2:
        return {}
    anchor = min(region_list, key=lambda region: region.id)
    return resolve_region_growth(
        anchor.id, to_rect(anchor), region_list, max_iterations=max_iterations
    )


def _overlap_violation(
    id_a: str, rect_a: Rect, id_b: str, rect_b: Rect, changed_region_id: str
) -> tuple[str | None, str | None]:
    """(grower_id, obstacle_id) for a partially overlapping pair whose shared
    intersection can't hold a card (MIN_REGION_SIZE: a card below whichever
    title bar sits at the overlap's top edge), or (None, None) if it can.

    Only the shared face is checked -- a region is NOT required to keep an
    area of its own outside the overlap (a card dropped into a sliver
    smaller than a card grows the region instead; see
    snapping.resolve_drop_with_growth). The side that grows is the one that
    wasn't gestured: whoever is being dragged or resized never grows for
    something it's passively involved in. With no gestured region in the
    pair (a downstream cascade) id_a grows, as a deterministic tie-break."""
    overlap = intersect(rect_a, rect_b)
    if overlap is not None and has_room_for_card(overlap, MIN_REGION_SIZE):
        return None, None
    grower_id = id_b if changed_region_id == id_a else id_a
    obstacle_id = id_b if grower_id == id_a else id_a
    return grower_id, obstacle_id
