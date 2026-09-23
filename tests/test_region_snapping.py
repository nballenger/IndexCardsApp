from indexcards.models.region import Region
from indexcards.regions.snapping import resolve_drop_against_regions


def _fully_inside(rect, region):
    x, y, width, height = rect
    return (
        x >= region.x
        and x + width <= region.x + region.width
        and y >= region.y
        and y + height <= region.y + region.height
    )


def _fully_outside(rect, region):
    x, y, width, height = rect
    return (
        x + width <= region.x
        or x >= region.x + region.width
        or y + height <= region.y
        or y >= region.y + region.height
    )


def test_no_regions_returns_zero_delta():
    assert resolve_drop_against_regions((0.0, 0.0, 200.0, 120.0), []) == (0.0, 0.0)


def test_already_fully_inside_returns_zero_delta():
    region = Region(id="r_1", x=0.0, y=0.0, width=400.0, height=300.0)
    rect = (50.0, 50.0, 200.0, 120.0)

    assert resolve_drop_against_regions(rect, [region]) == (0.0, 0.0)


def test_already_fully_outside_returns_zero_delta():
    region = Region(id="r_1", x=0.0, y=0.0, width=400.0, height=300.0)
    rect = (1000.0, 1000.0, 200.0, 120.0)

    assert resolve_drop_against_regions(rect, [region]) == (0.0, 0.0)


def test_flush_against_the_raw_edge_gets_pushed_in_to_clear_the_gutter():
    # Fully inside the region's RAW rect, but flush against its left edge
    # -- sitting inside the rounded-corner buffer this fix exists for.
    region = Region(id="r_1", x=0.0, y=0.0, width=400.0, height=300.0)
    rect = (0.0, 50.0, 200.0, 120.0)

    dx, dy = resolve_drop_against_regions(rect, [region])

    assert (dx, dy) == (16.0, 0.0)  # PLACEMENT_GUTTER


def test_sitting_under_the_label_bar_gets_pushed_below_it():
    region = Region(id="r_1", x=0.0, y=0.0, width=400.0, height=300.0)
    rect = (50.0, 0.0, 200.0, 120.0)

    dx, dy = resolve_drop_against_regions(rect, [region])

    assert (dx, dy) == (0.0, 28.0)  # LABEL_BAR_HEIGHT


def test_already_respecting_the_interior_is_untouched():
    region = Region(id="r_1", x=0.0, y=0.0, width=400.0, height=300.0)
    rect = (16.0, 28.0, 200.0, 120.0)  # exactly flush with the interior's own edges

    assert resolve_drop_against_regions(rect, [region]) == (0.0, 0.0)


def test_flush_against_the_exterior_raw_edge_is_untouched():
    # No gutter needed OUTSIDE a region -- the rounded corner only recedes
    # inward, it never bulges out, so exterior flush-adjacency looks fine.
    region = Region(id="r_1", x=0.0, y=0.0, width=400.0, height=300.0)
    rect = (400.0, 50.0, 200.0, 120.0)

    assert resolve_drop_against_regions(rect, [region]) == (0.0, 0.0)


def test_straddling_with_center_inside_snaps_fully_inside_on_one_axis():
    region = Region(id="r_1", x=0.0, y=0.0, width=400.0, height=300.0)
    rect = (250.0, 50.0, 200.0, 120.0)  # right edge at 450 (>400); center (350,110) inside

    dx, dy = resolve_drop_against_regions(rect, [region])

    x, y, width, height = rect
    new_rect = (x + dx, y + dy, width, height)
    assert _fully_inside(new_rect, region)
    assert dy == 0.0  # only the x-axis was violated


def test_straddling_with_center_inside_snaps_on_both_axes_from_a_corner():
    region = Region(id="r_1", x=0.0, y=0.0, width=400.0, height=300.0)
    rect = (280.0, 220.0, 200.0, 120.0)  # pokes past right (480) and bottom (340)

    dx, dy = resolve_drop_against_regions(rect, [region])

    x, y, width, height = rect
    new_rect = (x + dx, y + dy, width, height)
    assert _fully_inside(new_rect, region)
    assert dx < 0  # pushed left to clear the right edge
    assert dy < 0  # pushed up to clear the bottom edge


def test_straddling_with_center_outside_snaps_fully_outside_shorter_axis_wins():
    region = Region(id="r_1", x=0.0, y=0.0, width=400.0, height=300.0)
    rect = (350.0, 50.0, 200.0, 120.0)  # center (450, 110): outside on x

    dx, dy = resolve_drop_against_regions(rect, [region])

    x, y, width, height = rect
    new_rect = (x + dx, y + dy, width, height)
    assert _fully_outside(new_rect, region)
    assert dx > 0  # pushed further right (the shorter overlap axis)
    assert dy == 0.0


def test_item_wider_than_the_region_it_would_land_inside_returns_none():
    region = Region(id="r_1", x=0.0, y=0.0, width=150.0, height=300.0)  # narrower than a card
    rect = (50.0, 50.0, 200.0, 120.0)  # center (150, 110): inside region's span

    assert resolve_drop_against_regions(rect, [region]) is None


def test_nested_regions_both_satisfied_after_iterating():
    outer = Region(id="r_outer", x=0.0, y=0.0, width=600.0, height=400.0)
    inner = Region(id="r_inner", x=250.0, y=150.0, width=300.0, height=200.0)
    rect = (420.0, 200.0, 200.0, 120.0)  # center (520, 260): inside both

    dx, dy = resolve_drop_against_regions(rect, [outer, inner])

    x, y, width, height = rect
    new_rect = (x + dx, y + dy, width, height)
    assert _fully_inside(new_rect, outer)
    assert _fully_inside(new_rect, inner)


def test_result_is_independent_of_the_order_regions_are_passed_in():
    # The resolver sorts by area internally, so callers shouldn't have to
    # care what order they pass regions in -- same nested case as above,
    # checked both ways.
    outer = Region(id="r_outer", x=0.0, y=0.0, width=600.0, height=400.0)
    inner = Region(id="r_inner", x=250.0, y=150.0, width=300.0, height=200.0)
    rect = (420.0, 200.0, 200.0, 120.0)

    forward = resolve_drop_against_regions(rect, [outer, inner])
    reversed_order = resolve_drop_against_regions(rect, [inner, outer])

    assert forward == reversed_order
    x, y, width, height = rect
    new_rect = (x + forward[0], y + forward[1], width, height)
    assert _fully_inside(new_rect, outer)
    assert _fully_inside(new_rect, inner)


def test_unsatisfiable_configuration_returns_none_after_max_iterations():
    # Two same-size regions, each individually roomy enough to contain the
    # item on its own (interior width 228 >= 200), overlapping in only a
    # 40px-wide band -- too narrow to hold it in BOTH at once -- with both
    # demanding "inside" (the drop's center landed in the overlap).
    # Containing one always breaks containment of the other: a genuine,
    # unresolvable oscillation, not just a single region being too small.
    region_a = Region(id="r_a", x=0.0, y=0.0, width=260.0, height=180.0)
    region_b = Region(id="r_b", x=220.0, y=0.0, width=260.0, height=180.0)
    rect = (140.0, 30.0, 200.0, 120.0)  # center (240, 90): inside both

    assert resolve_drop_against_regions(rect, [region_a, region_b], max_iterations=4) is None
