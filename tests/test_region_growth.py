from indexcards.models.region import MIN_REGION_SIZE, Region
from indexcards.regions.growth import (
    grow_to_fit_intersection,
    grow_to_fit_obstacle,
    resolve_region_growth,
    yield_position_for_overlap,
)


def test_grow_to_fit_obstacle_already_satisfied_returns_none():
    outer = (0.0, 0.0, 600.0, 400.0)
    obstacle = (250.0, 150.0, 100.0, 100.0)  # small, roomy margins on every side

    assert grow_to_fit_obstacle(outer, obstacle) is None


def test_grow_to_fit_obstacle_grows_the_edge_with_the_smallest_deficit():
    outer = (0.0, 0.0, 300.0, 200.0)
    obstacle = (10.0, 10.0, 280.0, 180.0)  # thin 10px margins on all sides

    grown = grow_to_fit_obstacle(outer, obstacle)

    assert grown == (0.0, -150.0, 300.0, 350.0)
    # The chosen strip (the new area above the obstacle's own top edge)
    # now satisfies MIN_REGION_SIZE.
    min_w, min_h = MIN_REGION_SIZE
    obstacle_top = 10.0
    top_strip_height = obstacle_top - grown[1]
    assert grown[2] >= min_w
    assert top_strip_height >= min_h


def test_grow_to_fit_obstacle_ties_broken_left_before_right_top_bottom():
    outer = (0.0, 0.0, 500.0, 500.0)
    # Left/right margins (129px each) tie at a smaller deficit (111) than
    # top/bottom's (10px margins, deficit 150) -- confirms the winning
    # axis is picked correctly, then "left" wins the left/right tie.
    obstacle = (129.0, 10.0, 242.0, 480.0)

    assert grow_to_fit_obstacle(outer, obstacle) == (-111.0, 0.0, 611.0, 500.0)


def test_grow_to_fit_intersection_already_satisfied_returns_none():
    a = (0.0, 0.0, 300.0, 200.0)
    b = (0.0, 0.0, 300.0, 200.0)  # fully overlapping, already plenty big

    assert grow_to_fit_intersection(a, b) is None


def test_grow_to_fit_intersection_grows_toward_the_obstacle():
    a = (0.0, 0.0, 300.0, 200.0)
    b = (280.0, 0.0, 300.0, 200.0)  # overlap is only 20px wide

    grown = grow_to_fit_intersection(a, b)

    assert grown == (0.0, 0.0, 520.0, 200.0)
    # a's right edge now reaches far enough into b for a 240-wide overlap.
    new_overlap_width = (grown[0] + grown[2]) - 280.0
    assert new_overlap_width == MIN_REGION_SIZE[0]


def test_yield_position_for_overlap_pushes_dragged_fully_clear():
    dragged = (280.0, 0.0, 300.0, 200.0)
    target = (0.0, 0.0, 300.0, 200.0)

    result = yield_position_for_overlap(dragged, target)

    assert result == (300.0, 0.0, 300.0, 200.0)
    # Disjoint from target afterward.
    assert result[0] >= target[0] + target[2]


def test_resolve_region_growth_no_other_regions_returns_empty_diff():
    result = resolve_region_growth("r_new", (0.0, 0.0, 300.0, 200.0), [])

    assert result == {}


def test_resolve_region_growth_far_away_no_conflict_returns_empty_diff():
    regions = [Region(id="a", x=0.0, y=0.0, width=300.0, height=200.0)]

    result = resolve_region_growth("b", (1000.0, 1000.0, 300.0, 200.0), regions)

    assert result == {}


def test_resolve_region_growth_moat_violation_grows_only_the_container():
    outer = Region(id="outer", x=0.0, y=0.0, width=300.0, height=200.0)

    result = resolve_region_growth("inner", (10.0, 10.0, 250.0, 150.0), [outer])

    assert result == {"outer": (0.0, 0.0, 300.0, 320.0)}


def test_resolve_region_growth_two_children_with_enough_room_needs_no_growth():
    parent = Region(id="parent", x=0.0, y=0.0, width=800.0, height=300.0)
    child_1 = Region(id="child_1", x=10.0, y=10.0, width=240.0, height=160.0)

    result = resolve_region_growth(
        "child_2", (270.0, 10.0, 240.0, 160.0), [parent, child_1], try_yield=False
    )

    assert result == {}


def test_resolve_region_growth_overlap_without_yield_can_grow_both_sides():
    # 'a' isn't wide enough to absorb growing into the intersection without
    # also eating into 'b's own-only face, so this cascades: fixing the
    # shared intersection (growing 'a') breaks 'b's own face, which forces
    # 'b' itself to grow too (an own-face violation always means growing
    # that region -- no gesture-based exemption for it). Neither is
    # "yielding": there's no yield option here (try_yield=False).
    regions = [Region(id="a", x=0.0, y=0.0, width=300.0, height=200.0)]

    result = resolve_region_growth("b", (280.0, 0.0, 300.0, 200.0), regions, try_yield=False)

    assert result == {"a": (0.0, 0.0, 520.0, 200.0), "b": (280.0, -160.0, 300.0, 360.0)}


def test_resolve_region_growth_overlap_without_yield_clean_case_grows_only_target():
    # 'b' here is wide enough that growing 'a' into the intersection never
    # threatens 'b's own face, so only the non-gestured region ('a')
    # appears in the diff -- the common case, distinct from the cascading
    # one above.
    regions = [Region(id="a", x=0.0, y=0.0, width=300.0, height=200.0)]

    result = resolve_region_growth("b", (200.0, 0.0, 600.0, 200.0), regions, try_yield=False)

    assert result == {"a": (-40.0, 0.0, 480.0, 200.0)}


def test_resolve_region_growth_overlap_with_yield_moves_the_dragged_region_only():
    regions = [Region(id="a", x=0.0, y=0.0, width=300.0, height=200.0)]

    result = resolve_region_growth("b", (280.0, 0.0, 300.0, 200.0), regions, try_yield=True)

    assert result == {"b": (300.0, 0.0, 300.0, 200.0)}


def test_resolve_region_growth_gives_up_on_a_dense_cluster_within_default_iterations():
    # A real, naturally-occurring (not artificially capped) case: four
    # regions already clustered close together, plus a fifth landing in
    # the middle of them -- found via randomized search (see
    # test_region_growth_generative.py's own approach), and verified to
    # need more than the default 12 iterations (it converges by 50, so
    # this isn't infinite non-convergence, just a slow cascade) -- exactly
    # the kind of case the iteration cap exists to bail out of rather than
    # let a single gesture hang.
    regions = [
        Region(id="x0", x=253.33, y=227.39, width=265.23, height=175.54),
        Region(id="x1", x=153.38, y=121.48, width=287.03, height=178.20),
        Region(id="x2", x=142.98, y=175.01, width=294.49, height=190.28),
        Region(id="x3", x=84.55, y=226.74, width=277.10, height=175.03),
    ]
    changed_geometry = (272.92, 294.84, 288.61, 214.13)

    result = resolve_region_growth("new", changed_geometry, regions, try_yield=True)

    assert result is None


def test_resolve_region_growth_gives_up_after_max_iterations():
    # Unlike stage 2a's snapping (bounded translation only), growth has no
    # upper size limit, so most cascades DO eventually converge given
    # enough iterations -- this fixture (verified empirically, not by
    # hand) converges by iteration 8 with the default cap, so it only
    # demonstrates the max_iterations mechanism itself with an
    # artificially tight cap, not a fixture that's inherently
    # unresolvable. A real, naturally-occurring case that needs more than
    # the default 12 (a dense cluster of regions) is exercised by
    # tests/test_region_growth_generative.py instead.
    a = Region(id="a", x=0.0, y=0.0, width=240.0, height=160.0)

    result = resolve_region_growth("b", (100.0, 0.0, 240.0, 160.0), [a], max_iterations=3)

    assert result is None
