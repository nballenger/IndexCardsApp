from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from indexcards.arrange.auto_arrange import (
    ARRANGE_AVOIDANCE_GUTTER,
    TILE_GUTTER,
    auto_arrange_positions,
    positions_bbox,
    shift_layout_to_clear,
)
from indexcards.arrange.link_arrange import arrange_by_untangle_links
from indexcards.models.card import DEFAULT_CARD_SIZE, Card
from indexcards.models.link import Link
from indexcards.models.region import PLACEMENT_GUTTER, Region
from indexcards.models.stack import Stack
from indexcards.models.theme import Theme
from indexcards.regions.geometry import (
    Rect,
    contained_card_ids,
    contained_stack_ids,
    contains_point,
    interior_rect,
    relationship,
    to_corner_bbox,
    to_rect,
)
from indexcards.regions.growth import resolve_region_growth
from indexcards.regions.snapping import resolve_drop_against_regions

Position = tuple[float, float]


@dataclass
class RegionArrangeResult:
    card_positions: dict[str, Position] = field(default_factory=dict)
    stack_positions: dict[str, Position] = field(default_factory=dict)
    region_geometries: dict[str, Rect] = field(default_factory=dict)


def _layout(
    cards: list[Card],
    group_by: str,
    aspect_ratio: float,
    overflow_limit: int | None,
    theme: Theme | None,
    links: list[Link],
) -> dict[str, Position]:
    if group_by == "untangle":
        return arrange_by_untangle_links(cards, links, aspect_ratio)
    return auto_arrange_positions(
        cards, group_by, aspect_ratio=aspect_ratio, overflow_limit=overflow_limit, theme=theme
    )


def _shift_right_or_down(
    layout: dict[str, Position], obstacles: dict[str, Position], gutter: float
) -> dict[str, Position]:
    """Shifts layout just far enough right or down (whichever is smaller)
    to clear the combined bbox of obstacles. Unlike shift_layout_to_clear,
    never left/up: inside a region, left/up would push cards out over the
    region's own edge or title bar instead of growing the region."""
    lx1, ly1, lx2, ly2 = positions_bbox(layout)
    ox1, oy1, ox2, oy2 = positions_bbox(obstacles)
    if lx2 <= ox1 or lx1 >= ox2 or ly2 <= oy1 or ly1 >= oy2:
        return layout
    right, down = ox2 + gutter - lx1, oy2 + gutter - ly1
    dx, dy = (right, 0.0) if right <= down else (0.0, down)
    return {cid: (x + dx, y + dy) for cid, (x, y) in layout.items()}


_SCATTER_CANDIDATES = 12


def _compact_layout(
    cards: list[Card],
    group_by: str,
    aspect_ratio: float,
    overflow_limit: int | None,
    theme: Theme | None,
    links: list[Link],
) -> dict[str, Position]:
    """Scatter is randomized and its extent varies a lot run to run; since a
    region has to grow to hold whatever it produces, keep the most compact
    of a few candidates rather than a random sprawl. Every other mode is
    deterministic in extent, so it's laid out once."""
    candidates = _SCATTER_CANDIDATES if group_by == "scatter" else 1
    best: dict[str, Position] | None = None
    best_area = 0.0
    for _ in range(candidates):
        layout = _layout(cards, group_by, aspect_ratio, overflow_limit, theme, links)
        x1, y1, x2, y2 = positions_bbox(layout)
        area = (x2 - x1) * (y2 - y1)
        if best is None or area < best_area:
            best, best_area = layout, area
    return best


def _card_center(x: float, y: float) -> Position:
    return (x + DEFAULT_CARD_SIZE[0] / 2, y + DEFAULT_CARD_SIZE[1] / 2)


def _containing_ids(rects: dict[str, Rect], point: Position) -> frozenset[str]:
    return frozenset(rid for rid, rect in rects.items() if contains_point(rect, point))


def _has_partial_overlap(rects: dict[str, Rect], ids: Iterable[str]) -> bool:
    ids = sorted(ids)
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            if relationship(rects[a], rects[b]) == "overlap":
                return True
    return False


def _direct_parents(rects: dict[str, Rect]) -> dict[str, str | None]:
    """Each region's smallest strict container, or None. Identical rects
    tie-break by id so two regions can never each contain the other."""

    def area(rid: str) -> float:
        return rects[rid][2] * rects[rid][3]

    parents: dict[str, str | None] = {}
    for rid, rect in rects.items():
        containers = [
            other
            for other, other_rect in rects.items()
            if other != rid
            and relationship(other_rect, rect) == "a_contains_b"
            and (area(other) > area(rid) or (area(other) == area(rid) and other < rid))
        ]
        parents[rid] = min(containers, key=area) if containers else None
    return parents


def arrange_with_regions(
    cards: list[Card],
    stacks: list[Stack],
    regions: list[Region],
    group_by: str,
    *,
    aspect_ratio: float = 1.0,
    overflow_limit: int | None = None,
    theme: Theme | None = None,
    links: Iterable[Link] = (),
    ignore_pinned: bool = False,
) -> RegionArrangeResult | None:
    """Lays cards out by `group_by` (any auto_arrange_positions mode, or
    "untangle") inside each region -- each region's own loose cards
    tiled/scattered/columned within that region's interior, growing the
    region if they don't fit -- and the remaining unregioned cards in the
    free space around the (possibly grown) regions. `cards` are loose
    (unstacked) cards only. A region nested inside another moves as one
    rigid block (carrying everything inside it), shelf-packed below its
    parent's own loose cards; a card inside a partial overlap of two
    regions stays put, since where it sits carries meaning. Returns None
    if the growth invariants can't be satisfied after growing (the caller
    should leave everything alone), otherwise only what actually moved.

    ignore_pinned=True treats pinned cards like any other (Untangle Links
    already ignores pinned status)."""
    links = list(links)
    result = RegionArrangeResult()
    original = {region.id: to_rect(region) for region in regions}
    labels = {region.id: region.label for region in regions}
    geom: dict[str, Rect] = dict(original)
    parents = _direct_parents(original)
    kids: dict[str, list[str]] = {rid: [] for rid in original}
    for rid, parent in parents.items():
        if parent is not None:
            kids[parent].append(rid)

    def is_movable(card: Card) -> bool:
        return ignore_pinned or not card.pinned

    card_by_id = {card.id: card for card in cards}
    stack_by_id = {stack.id: stack for stack in stacks}
    card_pos: dict[str, Position] = {card.id: (card.x, card.y) for card in cards}
    stack_pos: dict[str, Position] = {stack.id: (stack.x, stack.y) for stack in stacks}
    moved_cards: set[str] = set()
    moved_stacks: set[str] = set()

    region_objs = {region.id: region for region in regions}
    all_card_ids = {
        rid: set(contained_card_ids(region_objs[rid], cards)) for rid in original
    }
    all_stack_ids = {
        rid: set(contained_stack_ids(region_objs[rid], stacks)) for rid in original
    }
    frozen_cards: set[str] = set()
    for card in cards:
        containing = _containing_ids(original, _card_center(card.x, card.y))
        if len(containing) >= 2 and _has_partial_overlap(original, containing):
            frozen_cards.add(card.id)

    def descendants(rid: str) -> list[str]:
        out: list[str] = []
        for kid in kids[rid]:
            out.append(kid)
            out.extend(descendants(kid))
        return out

    def translate_block(rid: str, dx: float, dy: float) -> None:
        for cid in all_card_ids[rid]:
            x, y = card_pos[cid]
            card_pos[cid] = (x + dx, y + dy)
            moved_cards.add(cid)
        for sid in all_stack_ids[rid]:
            x, y = stack_pos[sid]
            stack_pos[sid] = (x + dx, y + dy)
            moved_stacks.add(sid)
        for did in [rid, *descendants(rid)]:
            x, y, w, h = geom[did]
            geom[did] = (x + dx, y + dy, w, h)

    def process(rid: str) -> None:
        for kid in kids[rid]:
            process(kid)
        child_card_ids = set().union(*(all_card_ids[k] for k in kids[rid])) if kids[rid] else set()
        child_stack_ids = (
            set().union(*(all_stack_ids[k] for k in kids[rid])) if kids[rid] else set()
        )
        direct_cards = [
            card_by_id[cid] for cid in all_card_ids[rid] if cid not in child_card_ids
        ]
        members = [c for c in direct_cards if is_movable(c) and c.id not in frozen_cards]
        member_ids = {c.id for c in members}
        fixed_positions: dict[str, Position] = {
            c.id: card_pos[c.id] for c in direct_cards if c.id not in member_ids
        }
        fixed_positions.update(
            {sid: stack_pos[sid] for sid in all_stack_ids[rid] if sid not in child_stack_ids}
        )
        if not members and not kids[rid]:
            return

        x, y, width, height = geom[rid]
        ix, iy, iw, ih = interior_rect(geom[rid])
        aspect = iw / ih if iw > 0 and ih > 0 else aspect_ratio

        right, bottom = ix, iy
        if members:
            raw = _compact_layout(members, group_by, aspect, overflow_limit, theme, links)
            min_x, min_y, _, _ = positions_bbox(raw)
            layout = {cid: (px - min_x + ix, py - min_y + iy) for cid, (px, py) in raw.items()}
            if fixed_positions:
                layout = _shift_right_or_down(layout, fixed_positions, TILE_GUTTER)
            for cid, position in layout.items():
                card_pos[cid] = position
                moved_cards.add(cid)
            _, _, layout_right, layout_bottom = positions_bbox(layout)
            right, bottom = max(right, layout_right), max(bottom, layout_bottom)
        if fixed_positions:
            _, _, fixed_right, fixed_bottom = positions_bbox(fixed_positions)
            right, bottom = max(right, fixed_right), max(bottom, fixed_bottom)

        if kids[rid]:
            ordered = sorted(kids[rid], key=lambda k: (geom[k][1], geom[k][0], k))
            shelf_width = max(iw, right - ix, *(geom[k][2] for k in ordered))
            cursor_x = ix
            cursor_y = bottom + TILE_GUTTER if (members or fixed_positions) else iy
            row_height = 0.0
            for kid in ordered:
                kx, ky, kw, kh = geom[kid]
                if cursor_x > ix and cursor_x + kw > ix + shelf_width:
                    cursor_x = ix
                    cursor_y += row_height + TILE_GUTTER
                    row_height = 0.0
                translate_block(kid, cursor_x - kx, cursor_y - ky)
                cursor_x += kw + TILE_GUTTER
                row_height = max(row_height, kh)
                right = max(right, cursor_x - TILE_GUTTER)
                bottom = max(bottom, cursor_y + row_height)

        new_width = max(width, right - x + PLACEMENT_GUTTER)
        new_height = max(height, bottom - y + PLACEMENT_GUTTER)
        geom[rid] = (geom[rid][0], geom[rid][1], new_width, new_height)

    roots = [rid for rid, parent in parents.items() if parent is None]
    for root in roots:
        process(root)

    # Restore the growth invariants (moat, overlap room) for every region
    # whose size changed, inner regions first.
    grown = [rid for rid in geom if geom[rid][2:] != original[rid][2:]]
    grown.sort(key=lambda rid: geom[rid][2] * geom[rid][3])
    for rid in grown:
        current = [
            Region(id=k, x=g[0], y=g[1], width=g[2], height=g[3], label=labels[k])
            for k, g in geom.items()
        ]
        diff = resolve_region_growth(rid, geom[rid], current, try_yield=False)
        if diff is None:
            return None
        geom.update(diff)

    # Growth can extend a region over an item that stays put and change its
    # membership; move such an item clear rather than silently absorbing it.
    final_regions = [
        Region(id=k, x=g[0], y=g[1], width=g[2], height=g[3], label=labels[k])
        for k, g in geom.items()
    ]
    for item_id, (px, py) in list(
        {**{cid: card_pos[cid] for cid in card_pos if cid not in moved_cards},
         **{sid: stack_pos[sid] for sid in stack_pos if sid not in moved_stacks}}.items()
    ):
        before = _containing_ids(original, _card_center(px, py))
        if before == _containing_ids(
            {r.id: to_rect(r) for r in final_regions}, _card_center(px, py)
        ):
            continue
        delta = resolve_drop_against_regions(
            (px, py, *DEFAULT_CARD_SIZE), final_regions
        )
        if delta is None or delta == (0.0, 0.0):
            continue
        if item_id in card_by_id:
            card_pos[item_id] = (px + delta[0], py + delta[1])
            moved_cards.add(item_id)
        else:
            stack_pos[item_id] = (px + delta[0], py + delta[1])
            moved_stacks.add(item_id)

    # Free-space cards: everything loose, movable, and not in any region,
    # laid out clear of the FINAL region rectangles.
    in_any_region = set().union(*all_card_ids.values()) if all_card_ids else set()
    free = [c for c in cards if is_movable(c) and c.id not in in_any_region]
    if free:
        layout = _layout(free, group_by, aspect_ratio, overflow_limit, theme, links)
        obstacles = {
            c.id: card_pos[c.id]
            for c in cards
            if c.id not in in_any_region and not is_movable(c)
        }
        obstacles.update({sid: stack_pos[sid] for sid in stack_pos})
        layout = shift_layout_to_clear(
            layout,
            obstacles,
            ARRANGE_AVOIDANCE_GUTTER,
            extra_obstacle_bboxes=[to_corner_bbox(g) for g in geom.values()],
        )
        for cid, position in layout.items():
            card_pos[cid] = position
            moved_cards.add(cid)

    result.card_positions = {
        cid: card_pos[cid]
        for cid in moved_cards
        if card_pos[cid] != (card_by_id[cid].x, card_by_id[cid].y)
    }
    result.stack_positions = {
        sid: stack_pos[sid]
        for sid in moved_stacks
        if stack_pos[sid] != (stack_by_id[sid].x, stack_by_id[sid].y)
    }
    result.region_geometries = {rid: g for rid, g in geom.items() if g != original[rid]}
    return result

