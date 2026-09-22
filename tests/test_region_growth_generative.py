"""Randomized property check for regions/growth.py's room-for-a-card
invariant, per CLAUDE.md's own lesson that narrow unit tests have
previously passed on visibly-broken layout code in this project. The
checker below is deliberately NOT built from margin_strips/grow_to_fit_* --
it independently enumerates candidate placement corners (a standard
technique for axis-aligned rectangle-avoids-obstacles problems) rather than
clipping-and-stripping a single obstacle, so a bug shared between the
implementation and the checker can't hide a real violation. It targets the
same accepted simplifications the implementation itself targets (a
union-bbox moat for multiple children, pairwise-only overlap checking),
not a stricter ideal -- those simplifications are a deliberate, documented
trade-off, not something this test exists to flag.
"""

import random

from indexcards.models.region import MIN_REGION_SIZE
from indexcards.regions.growth import resolve_region_growth

_SEED_COUNT = 200
_STEPS_PER_SEED = 10
_COORD_RANGE = 1200.0
_MAX_REGIONS = 5


def _rects_overlap(a, b) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return not (ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay)


def _intersect(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    left, top = max(ax, bx), max(ay, by)
    right, bottom = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    if right <= left or bottom <= top:
        return None
    return (left, top, right - left, bottom - top)


def _independently_has_room(outer, obstacles, min_size=MIN_REGION_SIZE) -> bool:
    min_w, min_h = min_size
    ox, oy, ow, oh = outer
    if ow < min_w - 1e-9 or oh < min_h - 1e-9:
        return False
    xs = {ox, ox + ow - min_w}
    ys = {oy, oy + oh - min_h}
    for obs in obstacles:
        bx, by, bw, bh = obs
        xs.update({bx - min_w, bx + bw})
        ys.update({by - min_h, by + bh})
    for x in xs:
        if x < ox - 1e-9 or x + min_w > ox + ow + 1e-9:
            continue
        for y in ys:
            if y < oy - 1e-9 or y + min_h > oy + oh + 1e-9:
                continue
            candidate = (x, y, min_w, min_h)
            if not any(_rects_overlap(candidate, obstacle) for obstacle in obstacles):
                return True
    return False


def _relationship(a, b) -> str:
    overlap = _intersect(a, b)
    if overlap is None:
        return "disjoint"
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    if ax <= bx and ax + aw >= bx + bw and ay <= by and ay + ah >= by + bh:
        return "a_contains_b"
    if bx <= ax and bx + bw >= ax + aw and by <= ay and by + bh >= ay + ah:
        return "b_contains_a"
    return "overlap"


def _union(rects):
    rects = list(rects)
    left = min(r[0] for r in rects)
    top = min(r[1] for r in rects)
    right = max(r[0] + r[2] for r in rects)
    bottom = max(r[1] + r[3] for r in rects)
    return (left, top, right - left, bottom - top)


def _assert_invariant_holds(geometries: dict) -> None:
    ids = list(geometries)
    for container_id in ids:
        child_ids = [
            other_id
            for other_id in ids
            if other_id != container_id
            and _relationship(geometries[container_id], geometries[other_id]) == "a_contains_b"
        ]
        if not child_ids:
            continue
        children_union = _union(geometries[child_id] for child_id in child_ids)
        assert _independently_has_room(geometries[container_id], [children_union]), (
            f"moat violated: {container_id!r} vs children {child_ids!r}"
        )

    for i, id_a in enumerate(ids):
        for id_b in ids[i + 1 :]:
            rect_a, rect_b = geometries[id_a], geometries[id_b]
            if _relationship(rect_a, rect_b) != "overlap":
                continue
            assert _independently_has_room(rect_a, [rect_b]), f"own-face violated: {id_a!r}"
            assert _independently_has_room(rect_b, [rect_a]), f"own-face violated: {id_b!r}"
            overlap = _intersect(rect_a, rect_b)
            min_w, min_h = MIN_REGION_SIZE
            tolerance = 1e-6
            assert (
                overlap is not None
                and overlap[2] >= min_w - tolerance
                and overlap[3] >= min_h - tolerance
            ), f"intersection too small: {id_a!r}/{id_b!r}"


def _random_rect(rng: random.Random) -> tuple[float, float, float, float]:
    min_w, min_h = MIN_REGION_SIZE
    return (
        rng.uniform(0.0, _COORD_RANGE),
        rng.uniform(0.0, _COORD_RANGE),
        rng.uniform(min_w, min_w * 2),
        rng.uniform(min_h, min_h * 2),
    )


def _run_seed(seed: int) -> tuple[dict, int]:
    """Simulates a sequence of random region gestures, returns (final
    geometries, biggest single-step diff size) so the caller can flag
    unusually large cascades for closer inspection."""
    rng = random.Random(seed)
    geometries: dict[str, tuple] = {}
    next_id = 0
    biggest_diff = 0

    for _ in range(_STEPS_PER_SEED):
        existing_ids = list(geometries)
        if not existing_ids or (len(existing_ids) < _MAX_REGIONS and rng.random() < 0.4):
            region_id = f"r{next_id}"
            next_id += 1
            geometry = _random_rect(rng)
        else:
            region_id = rng.choice(existing_ids)
            gesture = rng.choice(["move", "resize"])
            x, y, width, height = geometries[region_id]
            if gesture == "move":
                geometry = (
                    rng.uniform(0.0, _COORD_RANGE),
                    rng.uniform(0.0, _COORD_RANGE),
                    width,
                    height,
                )
            else:
                min_w, min_h = MIN_REGION_SIZE
                geometry = (x, y, rng.uniform(min_w, min_w * 2), rng.uniform(min_h, min_h * 2))

        other_regions = [
            type("R", (), {"id": rid, "x": g[0], "y": g[1], "width": g[2], "height": g[3]})()
            for rid, g in geometries.items()
            if rid != region_id
        ]
        try_yield = rng.random() < 0.5
        diff = resolve_region_growth(region_id, geometry, other_regions, try_yield=try_yield)

        if diff is None:
            continue  # gesture reverted -- geometries unchanged, matching a real caller
        biggest_diff = max(biggest_diff, len(diff))
        # The diff only lists regions FORCED to change further (a
        # container needing a bigger moat, or the changed region itself
        # yielding) -- per resolve_region_growth's own contract, a real
        # caller always applies `geometry` (the originally requested new
        # state) for region_id itself, and the diff's entry for it (if
        # present) supersedes that.
        geometries[region_id] = geometry
        for changed_id, changed_geometry in diff.items():
            geometries[changed_id] = changed_geometry

        _assert_invariant_holds(geometries)

    return geometries, biggest_diff


def test_generative_room_for_a_card_invariant_holds_across_many_random_sequences():
    largest_cascade = (0, -1)
    for seed in range(_SEED_COUNT):
        _final_geometries, biggest_diff = _run_seed(seed)
        if biggest_diff > largest_cascade[0]:
            largest_cascade = (biggest_diff, seed)

    # Not a strict assertion on the cascade size itself -- just surfaces
    # which seed produced the biggest one, for the manual visual pass
    # described in the stage 2b plan (run that seed through a real
    # MainWindow and look at it) if this ever needs investigating.
    assert largest_cascade[1] >= 0 or _SEED_COUNT == 0
