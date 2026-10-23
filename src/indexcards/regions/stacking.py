from __future__ import annotations

from collections.abc import Callable, Iterable

from indexcards.models.region import LABEL_BAR_HEIGHT, LABEL_TEXT_MARGIN, Region
from indexcards.regions.geometry import Rect, intersect, relationship, to_rect

_DEFAULT_CHAR_WIDTH = 7.0


def _default_label_width(region: Region) -> float:
    return _DEFAULT_CHAR_WIDTH * len(region.label)


def stacking_order(
    regions: Iterable[Region],
    recency: Iterable[str] = (),
    label_width: Callable[[Region], float] | None = None,
    fix_titles: bool = True,
) -> list[str]:
    """Region ids from the bottom of the stack to the top. Purely derived
    from geometry (plus, within a session, which regions were moved most
    recently) -- never stored, so reopening a file recomputes it.

    1. Largest area at the bottom, ties by id: a smaller (more likely
       nested) region sits above a larger one.
    2. Every id in `recency` (oldest first) is raised to the top, then
       whatever is fully inside it is lifted back above it. An inner region
       is ALWAYS above the region containing it, here and below.
    3. With fix_titles, a pair of partially overlapping regions whose
       current order hides one's label text under the other's title bar is
       swapped when the other order hides nothing -- "make every title
       readable if possible". When neither order does, recency/area wins.
    """
    region_list = list(regions)
    rects: dict[str, Rect] = {region.id: to_rect(region) for region in region_list}
    by_id = {region.id: region for region in region_list}
    width_of = label_width or _default_label_width

    def area(rid: str) -> float:
        return rects[rid][2] * rects[rid][3]

    inside: dict[str, list[str]] = {
        rid: [
            other
            for other, rect in rects.items()
            if other != rid
            and rect != rects[rid]
            and relationship(rects[rid], rect) == "a_contains_b"
        ]
        for rid in rects
    }
    order = sorted(rects, key=lambda rid: (-area(rid), rid))

    def with_descendants(rid: str) -> list[str]:
        members = set(inside[rid])
        return [rid] + [other for other in order if other in members]

    def place(rid: str, above: str | None) -> None:
        """Move rid (and what's inside it) to just above `above`, or to the
        very top when above is None."""
        moving = with_descendants(rid)
        moving_set = set(moving)
        rest = [other for other in order if other not in moving_set]
        index = len(rest) if above is None else rest.index(above) + 1
        order[:] = rest[:index] + moving + rest[index:]

    def enforce_nesting() -> None:
        for _ in range(3 * len(order) + 3):
            for outer, inner_ids in inside.items():
                position = {rid: i for i, rid in enumerate(order)}
                broken = [d for d in inner_ids if position[d] < position[outer]]
                if broken:
                    place(broken[0], outer)
                    break
            else:
                return

    for rid in recency:
        if rid in rects:
            place(rid, None)

    if fix_titles:

        def covers(upper: str, lower: str) -> bool:
            lower_region = by_id[lower]
            if not lower_region.label:
                return False
            lx, ly, lw, _lh = rects[lower]
            text_width = min(width_of(lower_region), max(lw - 2 * LABEL_TEXT_MARGIN, 0.0))
            text = (lx + LABEL_TEXT_MARGIN, ly, text_width, LABEL_BAR_HEIGHT)
            ux, uy, uw, _uh = rects[upper]
            return intersect((ux, uy, uw, LABEL_BAR_HEIGHT), text) is not None

        ids = sorted(rects)
        for _ in range(2 * len(ids) + 2):
            position = {rid: i for i, rid in enumerate(order)}
            swapped = False
            for i, a in enumerate(ids):
                for b in ids[i + 1 :]:
                    if relationship(rects[a], rects[b]) != "overlap":
                        continue
                    lower, upper = (a, b) if position[a] < position[b] else (b, a)
                    if covers(upper, lower) and not covers(lower, upper):
                        place(lower, upper)
                        enforce_nesting()
                        swapped = True
                        break
                if swapped:
                    break
            if not swapped:
                break

    enforce_nesting()
    return list(order)
