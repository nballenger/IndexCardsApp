from indexcards.models.region import Region
from indexcards.regions.stacking import stacking_order


def _r(rid, x, y, w, h, label=""):
    return Region(id=rid, x=x, y=y, width=w, height=h, label=label)


def test_larger_regions_sit_below_smaller_ones_and_ties_go_by_id():
    regions = [
        _r("small", 0, 0, 300, 200),
        _r("big", 0, 0, 900, 700),
        _r("b", 2000, 0, 400, 300),
        _r("a", 3000, 0, 400, 300),
    ]

    assert stacking_order(regions) == ["big", "a", "b", "small"]


def test_the_most_recently_moved_region_goes_on_top_even_if_larger():
    regions = [_r("big", 0, 0, 900, 700), _r("small", 2000, 0, 300, 200)]

    assert stacking_order(regions, recency=["big"]) == ["small", "big"]


def test_recency_orders_by_oldest_first_newest_on_top():
    regions = [_r("a", 0, 0, 400, 300), _r("b", 2000, 0, 400, 300), _r("c", 4000, 0, 400, 300)]

    assert stacking_order(regions, recency=["b", "a"]) == ["c", "b", "a"]


def test_raising_an_outer_region_keeps_its_inner_region_above_it():
    regions = [
        _r("outer", 0, 0, 900, 700),
        _r("inner", 300, 250, 320, 300),
        _r("other", 2000, 0, 500, 400),
    ]

    order = stacking_order(regions, recency=["outer"])

    assert order.index("inner") > order.index("outer")
    assert order[-2:] == ["outer", "inner"]  # raised together, outer below its child


def test_an_inner_region_is_above_its_outer_even_when_older_in_recency():
    regions = [_r("outer", 0, 0, 900, 700), _r("inner", 300, 250, 320, 300)]

    order = stacking_order(regions, recency=["inner", "outer"])

    assert order == ["outer", "inner"]


def test_identical_regions_are_not_treated_as_nested():
    regions = [_r("a", 0, 0, 400, 300), _r("b", 0, 0, 400, 300)]

    assert sorted(stacking_order(regions)) == ["a", "b"]  # terminates, both present


def test_a_covered_title_is_lifted_when_the_swap_uncovers_it_without_hiding_the_other():
    # Equal size; b is to the right and on top (id order), its title bar
    # covers the label text of a (which starts at x=8 .. ~63). Move b so its
    # bar crosses a's label: a's text hidden, b's text (at b.x+8) is not
    # covered by a's bar.
    a = _r("a", 100, 0, 600, 400, "Alpha")
    b = _r("b", 0, 0, 160, 400, "Bravo")  # narrow: its bar covers a's label start (x 108..)
    regions = [a, b]
    # default order: same area? a is larger -> a below b -> b covers a's text.
    order = stacking_order(regions, fix_titles=False)
    assert order == ["a", "b"]

    fixed = stacking_order(regions, fix_titles=True)

    assert fixed == ["b", "a"]  # a lifted above b: both titles readable


def test_when_neither_order_keeps_both_titles_readable_the_recency_order_stays():
    # Both bars cover each other's label start: identical top edges, heavy overlap.
    a = _r("a", 0, 0, 600, 400, "Alpha")
    b = _r("b", 20, 0, 600, 400, "Bravo")

    first = stacking_order([a, b], recency=["a"])
    second = stacking_order([a, b], recency=["b"])

    assert first[-1] == "a" and second[-1] == "b"


def test_fix_up_never_puts_an_outer_region_above_its_inner():
    outer = _r("outer", 0, 0, 900, 700, "Outer")
    inner = _r("inner", 300, 250, 320, 300, "Inner")
    other = _r("other", 800, 200, 700, 500, "Other")

    order = stacking_order([outer, inner, other], recency=["other"])

    assert order.index("inner") > order.index("outer")


def test_the_title_fix_up_terminates_on_a_cycle_of_conflicts():
    regions = [
        _r("a", 0, 0, 500, 300, "Alpha"),
        _r("b", 30, 0, 500, 300, "Bravo"),
        _r("c", 60, 0, 500, 300, "Charlie"),
    ]

    order = stacking_order(regions)

    assert sorted(order) == ["a", "b", "c"]
