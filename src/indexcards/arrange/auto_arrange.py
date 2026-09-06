from __future__ import annotations

import math
import random

from indexcards.models.card import DEFAULT_CARD_SIZE, Card
from indexcards.models.link import Link
from indexcards.models.theme import Theme

STACK_SPACING_X = 260.0
CASCADE_OFFSET = 24.0
TILE_GUTTER = 24.0
SCATTER_MAX_OVERLAP_FRACTION = 0.10
SCATTER_NEIGHBOR_LENGTHS = 2  # "two card lengths" (card width) — see _scatter_reach
SCATTER_MAX_ATTEMPTS_PER_CARD = 20
COLUMN_GUTTER = 24.0
COLUMN_CATEGORY_GUTTER = COLUMN_GUTTER * 2


def _cascade_positions(cards: list[Card], origin_x: float) -> dict[str, tuple[float, float]]:
    return {
        card.id: (origin_x + CASCADE_OFFSET * i, CASCADE_OFFSET * i)
        for i, card in enumerate(cards)
    }


def arrange_by_color(cards: list[Card]) -> dict[str, tuple[float, float]]:
    """One stack per distinct color slot present, ordered by slot id for
    stable output."""
    groups: dict[str, list[Card]] = {}
    for card in cards:
        groups.setdefault(card.color_slot, []).append(card)

    positions: dict[str, tuple[float, float]] = {}
    for i, slot_id in enumerate(sorted(groups)):
        positions.update(_cascade_positions(groups[slot_id], i * STACK_SPACING_X))
    return positions


def _lay_out_columns(
    categories: list[list[Card]], overflow_limit: int | None
) -> dict[str, tuple[float, float]]:
    """Places each category's cards into one or more single-file vertical
    columns, all sharing the same top edge (y=0) and growing downward —
    like an upside-down bar chart. A category whose card count exceeds
    overflow_limit spills into additional "overflow" columns (filled
    column-major: the first overflow_limit cards fill column 1, the next
    overflow_limit fill column 2, and so on) separated from each other by
    a single COLUMN_GUTTER, same as the vertical gap between cards within
    a column. Only the boundary between two different categories gets the
    wider COLUMN_CATEGORY_GUTTER, so the doubled gap reads as "new group"
    rather than just "another overflow column"."""
    width, height = DEFAULT_CARD_SIZE
    positions: dict[str, tuple[float, float]] = {}
    x = 0.0
    is_first_column = True
    for category_cards in categories:
        if not category_cards:
            continue
        limit = overflow_limit if overflow_limit is not None else len(category_cards)
        subcolumns = [category_cards[i : i + limit] for i in range(0, len(category_cards), limit)]
        for subcolumn_index, subcolumn in enumerate(subcolumns):
            if is_first_column:
                is_first_column = False
            else:
                gutter = COLUMN_GUTTER if subcolumn_index > 0 else COLUMN_CATEGORY_GUTTER
                x += width + gutter
            for row, card in enumerate(subcolumn):
                positions[card.id] = (x, row * (height + COLUMN_GUTTER))
    return positions


def _color_category_order(slot_ids: set[str], theme: Theme) -> list[str]:
    """Theme slots first, in the theme's own defined order (matching the
    card color-picker's swatch order) and non-orphaned before orphaned
    within that — then any slot id not found in the theme at all (e.g.
    from hand-edited data) sorted by id after."""
    theme_order = [slot.id for slot in theme.slots if not slot.orphaned]
    theme_order += [slot.id for slot in theme.slots if slot.orphaned]
    known = [slot_id for slot_id in theme_order if slot_id in slot_ids]
    unknown = sorted(slot_id for slot_id in slot_ids if slot_id not in theme_order)
    return known + unknown


def arrange_by_columns_color(
    cards: list[Card], theme: Theme, overflow_limit: int | None = None
) -> dict[str, tuple[float, float]]:
    """One column-group per distinct color slot, ordered per
    _color_category_order; within each, cards sort alphabetically (case
    sensitive) by text."""
    groups: dict[str, list[Card]] = {}
    for card in cards:
        groups.setdefault(card.color_slot, []).append(card)

    categories = [
        sorted(groups[slot_id], key=lambda card: card.text)
        for slot_id in _color_category_order(set(groups), theme)
    ]
    return _lay_out_columns(categories, overflow_limit)


def _alphabetical_key(card: Card) -> str:
    return card.text[:1].lower()


def arrange_by_columns_alphabetical(
    cards: list[Card], overflow_limit: int | None = None
) -> dict[str, tuple[float, float]]:
    """One column-group per distinct lowercased first character of the
    card's text (case insensitive); cards with blank text form their own
    group, sorted last. Within each group, cards sort alphabetically
    (case sensitive) by text."""
    groups: dict[str, list[Card]] = {}
    for card in cards:
        groups.setdefault(_alphabetical_key(card), []).append(card)

    ordered_keys = sorted(groups, key=lambda key: (key == "", key))
    categories = [sorted(groups[key], key=lambda card: card.text) for key in ordered_keys]
    return _lay_out_columns(categories, overflow_limit)


def arrange_by_tag(cards: list[Card], tag: str) -> dict[str, tuple[float, float]]:
    """Two stacks: cards that have `tag`, and cards that don't."""
    has_tag = [card for card in cards if tag in card.tags]
    no_tag = [card for card in cards if tag not in card.tags]

    positions: dict[str, tuple[float, float]] = {}
    positions.update(_cascade_positions(has_tag, 0.0))
    positions.update(_cascade_positions(no_tag, STACK_SPACING_X))
    return positions


def arrange_by_tile(
    cards: list[Card], aspect_ratio: float = 1.0, rng: random.Random | None = None
) -> dict[str, tuple[float, float]]:
    """Lays cards out in a row/column grid, with a small gutter between
    cells. The number of columns is chosen so the overall grid's own
    width:height roughly matches aspect_ratio (e.g. a wide viewport gets
    a wide, short grid rather than a tall, narrow one).

    Which card lands in which cell isn't meant to be significant, so the
    placement order is explicitly randomized rather than left to happen
    to follow whatever order `cards` was given in (typically document/
    creation order) — otherwise the grid would end up incidentally
    ordered by creation time every time, which isn't actually part of
    what this mode promises."""
    if not cards:
        return {}
    if rng is None:
        rng = random.Random()
    shuffled = list(cards)
    rng.shuffle(shuffled)

    width, height = DEFAULT_CARD_SIZE
    columns = max(1, round(math.sqrt(len(cards) * aspect_ratio)))
    positions: dict[str, tuple[float, float]] = {}
    for i, card in enumerate(shuffled):
        row, column = divmod(i, columns)
        positions[card.id] = (
            column * (width + TILE_GUTTER),
            row * (height + TILE_GUTTER),
        )
    return positions


def _overlap_area(
    pos_a: tuple[float, float], pos_b: tuple[float, float], width: float, height: float
) -> float:
    ax, ay = pos_a
    bx, by = pos_b
    overlap_x = max(0.0, min(ax + width, bx + width) - max(ax, bx))
    overlap_y = max(0.0, min(ay + height, by + height) - max(ay, by))
    return overlap_x * overlap_y


def _max_overlap_fraction(
    candidate: tuple[float, float],
    placed: list[tuple[float, float]],
    width: float,
    height: float,
) -> float:
    card_area = width * height
    return max(
        (_overlap_area(candidate, other, width, height) / card_area for other in placed),
        default=0.0,
    )


PASTE_OVERLAP_THRESHOLD = 0.5  # "substantially on top of" an existing card
PASTE_NUDGE_OFFSET = CASCADE_OFFSET
PASTE_MAX_NUDGES = 50


def avoid_card_overlap(
    position: tuple[float, float],
    obstacle_positions: list[tuple[float, float]],
    width: float = DEFAULT_CARD_SIZE[0],
    height: float = DEFAULT_CARD_SIZE[1],
) -> tuple[float, float]:
    """Nudges `position` diagonally by PASTE_NUDGE_OFFSET, repeatedly, until
    its overlap with every obstacle in obstacle_positions is below
    PASTE_OVERLAP_THRESHOLD (bounded by PASTE_MAX_NUDGES, so this always
    terminates — same reasoning as arrange_by_scatter's own attempt cap).
    Used when pasting: repeated pastes of the same clipboard content would
    otherwise all land at the exact same recentered position, perfectly
    overlapping each other and whatever was already there."""
    x, y = position
    for _ in range(PASTE_MAX_NUDGES):
        overlap = _max_overlap_fraction((x, y), obstacle_positions, width, height)
        if overlap < PASTE_OVERLAP_THRESHOLD:
            return (x, y)
        x += PASTE_NUDGE_OFFSET
        y += PASTE_NUDGE_OFFSET
    return (x, y)


def _scatter_reach(aspect_ratio: float) -> tuple[float, float]:
    """The (max_dx, max_dy) reach of the elliptical search neighborhood
    used to place each new scattered card, in scene units.

    A plain circle (the same reach in every direction, i.e. aspect_ratio
    == 1 below) was measured — across hundreds of random seeds and
    several card counts — to already produce, on average, a roughly
    square cluster: an earlier version of this function instead sized
    the reach per-axis to the card's own width/height specifically to
    "fix" an assumed card-shape-driven bias, but that reasoning only
    held up for a single anchor-to-candidate check; once you account for
    a candidate needing to clear *every* already-placed card (not just
    its anchor), that per-axis version measurably over-corrected into a
    strong, consistent bias toward wide clusters instead. So the base
    reach here stays an isotropic circle of SCATTER_NEIGHBOR_LENGTHS card
    lengths (using the card's width as its "length", matching how the
    constraint was originally specified).

    Scaling that circle's two radii by sqrt(aspect_ratio) and
    1/sqrt(aspect_ratio) — which preserves its area, only reshaping it —
    then deliberately skews the search (and so the resulting cluster) to
    roughly track the canvas viewport's own aspect ratio: verified
    empirically to track closely (e.g. aspect_ratio=3 yields an average
    cluster width:height ratio of ~3 too), so a wide window tends to
    produce a wide cluster and needs less re-zooming to show it all
    afterward. An aspect_ratio of 1 (or an invalid one) leaves both radii
    at the unskewed, empirically-neutral circle.
    """
    width, _height = DEFAULT_CARD_SIZE
    base_reach = SCATTER_NEIGHBOR_LENGTHS * width
    scale = math.sqrt(aspect_ratio) if aspect_ratio > 0 else 1.0
    max_dx = base_reach * scale
    max_dy = base_reach / scale
    return max_dx, max_dy


def arrange_by_scatter(
    cards: list[Card], aspect_ratio: float = 1.0, rng: random.Random | None = None
) -> dict[str, tuple[float, float]]:
    """Randomly scatters cards so they cluster loosely around each other
    rather than overlapping heavily or spreading out arbitrarily far:
    the first card is placed at the origin (the view is centered/panned
    onto the result afterward, same as every other arrange mode); each
    later card picks a random already-placed card as an anchor and tries
    up to SCATTER_MAX_ATTEMPTS_PER_CARD random points within an ellipse
    around it (see _scatter_reach), accepting the first one that
    overlaps no already-placed card by more than
    SCATTER_MAX_OVERLAP_FRACTION of its area. If none of those attempts
    qualifies, it falls back to whichever candidate overlapped the least,
    so placement always terminates rather than retrying forever."""
    if not cards:
        return {}
    if rng is None:
        rng = random.Random()

    width, height = DEFAULT_CARD_SIZE
    max_dx, max_dy = _scatter_reach(aspect_ratio)
    positions: dict[str, tuple[float, float]] = {cards[0].id: (0.0, 0.0)}
    placed = [(0.0, 0.0)]

    for card in cards[1:]:
        anchor = rng.choice(placed)
        best_candidate = None
        best_overlap = math.inf
        for _attempt in range(SCATTER_MAX_ATTEMPTS_PER_CARD):
            angle = rng.uniform(0.0, 2 * math.pi)
            r = rng.uniform(0.0, 1.0)
            candidate = (
                anchor[0] + max_dx * r * math.cos(angle),
                anchor[1] + max_dy * r * math.sin(angle),
            )
            overlap = _max_overlap_fraction(candidate, placed, width, height)
            if overlap < best_overlap:
                best_candidate, best_overlap = candidate, overlap
            if overlap <= SCATTER_MAX_OVERLAP_FRACTION:
                break

        positions[card.id] = best_candidate
        placed.append(best_candidate)

    return positions


def auto_arrange_positions(
    cards: list[Card],
    group_by: str,
    tag: str | None = None,
    aspect_ratio: float = 1.0,
    overflow_limit: int | None = None,
    theme: Theme | None = None,
    links: list[Link] | None = None,
) -> dict[str, tuple[float, float]]:
    if group_by == "color":
        return arrange_by_color(cards)
    if group_by == "tag":
        if not tag:
            raise ValueError("tag is required when group_by='tag'")
        return arrange_by_tag(cards, tag)
    if group_by == "tile":
        return arrange_by_tile(cards, aspect_ratio)
    if group_by == "scatter":
        return arrange_by_scatter(cards, aspect_ratio)
    if group_by == "columns_color":
        if theme is None:
            raise ValueError("theme is required when group_by='columns_color'")
        return arrange_by_columns_color(cards, theme, overflow_limit)
    if group_by == "columns_alphabetical":
        return arrange_by_columns_alphabetical(cards, overflow_limit)
    if group_by == "untangle_links":
        if links is None:
            raise ValueError("links is required when group_by='untangle_links'")
        # Deferred import: link_arrange.py imports arrange_by_tile/
        # positions_bbox from this module at its own module scope, so a
        # top-level import here would be circular.
        from indexcards.arrange.link_arrange import arrange_by_untangle_links

        return arrange_by_untangle_links(cards, links, aspect_ratio)
    raise ValueError(f"unknown group_by: {group_by!r}")


ARRANGE_AVOIDANCE_GUTTER = 40.0
STACK_EXPLODE_GUTTER = 40.0


def positions_bbox(
    positions: dict[str, tuple[float, float]],
) -> tuple[float, float, float, float]:
    """(min_x, min_y, max_x, max_y) covering every card's full footprint
    (not just its top-left position point) at the given positions."""
    width, height = DEFAULT_CARD_SIZE
    xs = [x for x, _y in positions.values()]
    ys = [y for _x, y in positions.values()]
    return (min(xs), min(ys), max(xs) + width, max(ys) + height)


def _shift_to_clear_overlap(
    moving_bbox: tuple[float, float, float, float],
    fixed_bbox: tuple[float, float, float, float],
    gutter: float,
) -> tuple[float, float]:
    """(dx, dy) to translate moving_bbox by so it no longer overlaps
    fixed_bbox (with gutter of clearance), choosing whichever of the four
    cardinal directions requires the smallest shift. (0.0, 0.0) if they
    don't overlap already."""
    mx1, my1, mx2, my2 = moving_bbox
    fx1, fy1, fx2, fy2 = fixed_bbox
    if mx2 <= fx1 or mx1 >= fx2 or my2 <= fy1 or my1 >= fy2:
        return (0.0, 0.0)

    shift_right = (fx2 - mx1) + gutter
    shift_left = (fx1 - mx2) - gutter
    shift_down = (fy2 - my1) + gutter
    shift_up = (fy1 - my2) - gutter
    candidates = [
        (shift_right, 0.0),
        (shift_left, 0.0),
        (0.0, shift_down),
        (0.0, shift_up),
    ]
    return min(candidates, key=lambda shift: abs(shift[0]) + abs(shift[1]))


def arrange_avoiding_obstacles(
    cards: list[Card],
    group_by: str,
    tag: str | None = None,
    aspect_ratio: float = 1.0,
    overflow_limit: int | None = None,
    theme: Theme | None = None,
    stack_positions: dict[str, tuple[float, float]] | None = None,
    links: list[Link] | None = None,
) -> dict[str, tuple[float, float]]:
    """Like auto_arrange_positions, but leaves every pinned card and every
    Stack box exactly where it is, treating both as fixed obstacles —
    only unpinned cards get a freshly computed layout, which is then
    shifted (preserving its own internal arrangement) just far enough to
    clear the combined bounding box of the pinned cards and stacks, if it
    would otherwise overlap either. Returns positions only for the cards
    that actually moved (pinned card ids aren't included), or {} if every
    card is pinned."""
    pinned = [card for card in cards if card.pinned]
    unpinned = [card for card in cards if not card.pinned]
    if not unpinned:
        return {}

    new_positions = auto_arrange_positions(
        unpinned,
        group_by,
        tag,
        aspect_ratio=aspect_ratio,
        overflow_limit=overflow_limit,
        theme=theme,
        links=links,
    )
    obstacles = {card.id: (card.x, card.y) for card in pinned}
    obstacles.update(stack_positions or {})
    if not obstacles:
        return new_positions

    return shift_layout_to_clear(new_positions, obstacles, ARRANGE_AVOIDANCE_GUTTER)


def shift_layout_to_clear(
    layout: dict[str, tuple[float, float]],
    obstacle_positions: dict[str, tuple[float, float]],
    gutter: float = STACK_EXPLODE_GUTTER,
) -> dict[str, tuple[float, float]]:
    """Shifts every position in layout by the same (dx, dy) — just enough
    to clear obstacle_positions' bounding box (with gutter clearance),
    preserving layout's own internal arrangement. Returns layout unchanged
    if either dict is empty or they don't already overlap."""
    if not layout or not obstacle_positions:
        return layout
    layout_bbox = positions_bbox(layout)
    obstacle_bbox = positions_bbox(obstacle_positions)
    dx, dy = _shift_to_clear_overlap(layout_bbox, obstacle_bbox, gutter)
    if dx == 0.0 and dy == 0.0:
        return layout
    return {item_id: (x + dx, y + dy) for item_id, (x, y) in layout.items()}


GATHER_STACKS_GUTTER = 40.0


def union_bbox(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> tuple[float, float, float, float]:
    """The smallest bbox containing both a and b."""
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _expand_bbox_to_aspect_ratio(
    bbox: tuple[float, float, float, float], aspect_ratio: float
) -> tuple[float, float, float, float]:
    """Grows the shorter dimension of bbox about its own center so its
    width:height ratio matches aspect_ratio exactly. Never shrinks either
    dimension, so the result always still contains bbox. A non-positive
    height or aspect_ratio leaves bbox unchanged (nothing sane to compute)."""
    x1, y1, x2, y2 = bbox
    width, height = x2 - x1, y2 - y1
    if height <= 0 or aspect_ratio <= 0:
        return bbox
    center_x, center_y = (x1 + x2) / 2, (y1 + y2) / 2
    if width / height > aspect_ratio:
        new_width, new_height = width, width / aspect_ratio
    else:
        new_width, new_height = height * aspect_ratio, height
    return (
        center_x - new_width / 2,
        center_y - new_height / 2,
        center_x + new_width / 2,
        center_y + new_height / 2,
    )


CENTER_RECT_MARGIN = ARRANGE_AVOIDANCE_GUTTER
CENTER_RECT_CONTENT_FRACTION = 0.5


def compute_center_rect(
    pinned_positions: dict[str, tuple[float, float]],
    all_content_bbox: tuple[float, float, float, float] | None,
    aspect_ratio: float,
    margin: float = CENTER_RECT_MARGIN,
) -> tuple[float, float, float, float]:
    """The central "workspace" rectangle that Tidy/Sweep to Edges clears.

    With pinned cards, it's sized to just contain them (plus margin) — the
    workspace forms around whatever the user has already anchored in
    place. With none, it defaults to CENTER_RECT_CONTENT_FRACTION of the
    current content's bounding box, floored at a 4x3 grid of cards' worth
    of space (so a mostly-empty canvas still gets a usable-sized
    workspace) and centered on that content — or, on a fully empty
    canvas, just that floor centered at the origin. Either way, the
    result is padded by `margin` and expanded to match aspect_ratio.
    """
    width, height = DEFAULT_CARD_SIZE
    if pinned_positions:
        seed = positions_bbox(pinned_positions)
    else:
        floor_width = 4 * width + 3 * TILE_GUTTER
        floor_height = 3 * height + 2 * TILE_GUTTER
        if all_content_bbox is not None:
            bx1, by1, bx2, by2 = all_content_bbox
            center_x, center_y = (bx1 + bx2) / 2, (by1 + by2) / 2
            seed_width = max(floor_width, (bx2 - bx1) * CENTER_RECT_CONTENT_FRACTION)
            seed_height = max(floor_height, (by2 - by1) * CENTER_RECT_CONTENT_FRACTION)
        else:
            center_x, center_y = 0.0, 0.0
            seed_width, seed_height = floor_width, floor_height
        seed = (
            center_x - seed_width / 2,
            center_y - seed_height / 2,
            center_x + seed_width / 2,
            center_y + seed_height / 2,
        )

    padded = (seed[0] - margin, seed[1] - margin, seed[2] + margin, seed[3] + margin)
    return _expand_bbox_to_aspect_ratio(padded, aspect_ratio)


def _spiral_start(
    center_rect: tuple[float, float, float, float], gather_edge: str
) -> tuple[tuple[float, float], str, dict[str, float]]:
    """The first card position, initial walk direction, and initial
    per-side limits for arrange_cards_tidy_to_edges, chosen so the first
    leg traced is gather_edge's own side (then its clockwise neighbor,
    etc.) — the side whose limit isn't listed here starts pre-offset to
    that first card's own outer edge (there's nothing else to compare
    against yet, since the walk begins mid-leg on that side); the other
    three limits start at center_rect's raw edges, untouched until the
    walk actually reaches them."""
    width, height = DEFAULT_CARD_SIZE
    x1, y1, x2, y2 = center_rect
    limits = {"top": y1, "right": x2, "bottom": y2, "left": x1}
    if gather_edge == "top":
        limits["top"] = y1 - height
        return (x1, y1 - height), "right", limits
    if gather_edge == "right":
        limits["right"] = x2 + width
        return (x2, y1), "down", limits
    if gather_edge == "bottom":
        limits["bottom"] = y2 + height
        return (x2 - width, y2), "left", limits
    if gather_edge == "left":
        limits["left"] = x1 - width
        return (x1 - width, y2 - height), "up", limits
    raise ValueError(f"unknown edge: {gather_edge!r}")


def arrange_cards_tidy_to_edges(
    cards: list[Card],
    center_rect: tuple[float, float, float, float],
    gather_edge: str,
    rng: random.Random | None = None,
) -> dict[str, tuple[float, float]]:
    """Tiles cards around center_rect in one continuous clockwise spiral,
    starting flush against gather_edge's own side. The walk moves one
    card-and-gutter step at a time; when a placed card's outer edge first
    crosses the current side's limit, that card becomes the pivot — the
    limit updates to that card's own outer edge (so the next lap around
    starts from there instead of the original rect) and the walk turns
    90 degrees clockwise. This keeps a large batch spiraling outward as a
    connected, corner-clean frame — each pivot card is shared between the
    two legs it joins, so there's never a gap or overlap at a turn —
    rather than tiling each side independently and hoping the corners
    line up. Which card lands in which slot isn't meant to be
    significant, so order is randomized, same rationale as
    arrange_by_tile."""
    if not cards:
        return {}
    if rng is None:
        rng = random.Random()
    shuffled = list(cards)
    rng.shuffle(shuffled)

    width, height = DEFAULT_CARD_SIZE
    step_x, step_y = width + TILE_GUTTER, height + TILE_GUTTER
    (x, y), direction, limits = _spiral_start(center_rect, gather_edge)

    slots: list[tuple[float, float]] = []
    while len(slots) < len(cards):
        slots.append((x, y))
        if direction == "right":
            if x > limits["right"]:
                limits["right"] = x + width
                direction, y = "down", y + step_y
            else:
                x += step_x
        elif direction == "down":
            if y > limits["bottom"]:
                limits["bottom"] = y + height
                direction, x = "left", x - step_x
            else:
                y += step_y
        elif direction == "left":
            if x + width < limits["left"]:
                limits["left"] = x
                direction, y = "up", y - step_y
            else:
                x -= step_x
        else:  # direction == "up"
            if y + height < limits["top"]:
                limits["top"] = y
                direction, x = "right", x + step_x
            else:
                y -= step_y

    return {card.id: slot for card, slot in zip(shuffled, slots[: len(cards)], strict=True)}


SWEEP_SINGLE_SIDE_THRESHOLD = 9
SWEEP_MAX_DEPTH_GROWTHS = 12


def _side_band(
    side: str, center_rect: tuple[float, float, float, float], depth: float
) -> tuple[float, float, float, float]:
    """The exterior rectangle of `depth` thickness hugging one side of
    center_rect, spanning exactly that side's own length (no corner
    extension) — used for the single-side Sweep case, where there's no
    adjacent side to seam with."""
    x1, y1, x2, y2 = center_rect
    if side == "top":
        return (x1, y1 - depth, x2, y1)
    if side == "bottom":
        return (x1, y2, x2, y2 + depth)
    if side == "left":
        return (x1 - depth, y1, x1, y2)
    if side == "right":
        return (x2, y1, x2 + depth, y2)
    raise ValueError(f"unknown side: {side!r}")


def _full_frame_bands(
    center_rect: tuple[float, float, float, float], depth: float
) -> list[tuple[float, float, float, float]]:
    """Four non-overlapping rectangles that together tile the whole
    exterior frame of `depth` thickness around center_rect, corners
    included (top/bottom bands run the full extended width; left/right
    bands fill in just the rect's own height between them)."""
    x1, y1, x2, y2 = center_rect
    return [
        (x1 - depth, y1 - depth, x2 + depth, y1),  # top
        (x1 - depth, y2, x2 + depth, y2 + depth),  # bottom
        (x1 - depth, y1, x1, y2),  # left
        (x2, y1, x2 + depth, y2),  # right
    ]


def _sample_point_in_band(
    band: tuple[float, float, float, float], width: float, height: float, rng: random.Random
) -> tuple[float, float]:
    bx1, by1, bx2, by2 = band
    max_x, max_y = max(bx1, bx2 - width), max(by1, by2 - height)
    x = rng.uniform(bx1, max_x) if max_x > bx1 else bx1
    y = rng.uniform(by1, max_y) if max_y > by1 else by1
    return (x, y)


def arrange_cards_sweep_to_edges(
    cards: list[Card],
    center_rect: tuple[float, float, float, float],
    gather_edge: str,
    rng: random.Random | None = None,
) -> dict[str, tuple[float, float]]:
    """Scatters cards loosely around the outside of center_rect, reusing
    the same rejection-sampling approach as arrange_by_scatter (accept the
    first candidate overlapping no already-placed card by more than
    SCATTER_MAX_OVERLAP_FRACTION, else fall back to the least-overlapping
    one tried).

    Below SWEEP_SINGLE_SIDE_THRESHOLD cards, the scatter is confined to a
    single band on gather_edge; at or above it, cards scatter across the
    full exterior frame regardless of how high the count goes. Either way
    the band/frame depth starts at one card-length plus a gutter and grows
    in that same increment, up to SWEEP_MAX_DEPTH_GROWTHS times, whenever a
    card can't find a low-overlap spot — guaranteeing placement always
    terminates rather than retrying forever."""
    if not cards:
        return {}
    if rng is None:
        rng = random.Random()

    width, height = DEFAULT_CARD_SIZE
    depth_increment = max(width, height) + TILE_GUTTER
    depth = depth_increment
    single_side = len(cards) < SWEEP_SINGLE_SIDE_THRESHOLD

    positions: dict[str, tuple[float, float]] = {}
    placed: list[tuple[float, float]] = []

    for card in cards:
        for growth in range(SWEEP_MAX_DEPTH_GROWTHS):
            bands = (
                [_side_band(gather_edge, center_rect, depth)]
                if single_side
                else _full_frame_bands(center_rect, depth)
            )
            if len(bands) > 1:
                weights = [max(0.0, (b[2] - b[0]) * (b[3] - b[1])) for b in bands]
                band = rng.choices(bands, weights=weights, k=1)[0]
            else:
                band = bands[0]

            best_candidate = None
            best_overlap = math.inf
            for _attempt in range(SCATTER_MAX_ATTEMPTS_PER_CARD):
                candidate = _sample_point_in_band(band, width, height, rng)
                overlap = _max_overlap_fraction(candidate, placed, width, height)
                if overlap < best_overlap:
                    best_candidate, best_overlap = candidate, overlap
                if overlap <= SCATTER_MAX_OVERLAP_FRACTION:
                    break

            is_last_growth = growth == SWEEP_MAX_DEPTH_GROWTHS - 1
            if best_overlap <= SCATTER_MAX_OVERLAP_FRACTION or is_last_growth:
                positions[card.id] = best_candidate
                placed.append(best_candidate)
                break
            depth += depth_increment

    return positions


def arrange_stacks_to_edge(
    stacks: list[Card],
    edge: str,
    cards_bbox: tuple[float, float, float, float] | None,
    gutter: float = GATHER_STACKS_GUTTER,
) -> dict[str, tuple[float, float]]:
    """Lines every stack up into a single column (edge="left"/"right") or
    single row (edge="top"/"bottom"), placed just outside cards_bbox — the
    bounding box of every card currently loose on the canvas, i.e. the
    "occupied area" a gathered column/row should sit clear of rather than
    the extreme edge of the available space — on the named side, with
    gutter clearance between the stacks and that bbox. Order along the
    column/row follows `stacks` as given (document order — this makes no
    ordering decision of its own). cards_bbox=None (nothing on the canvas
    to gather away from) anchors the column/row at the origin instead."""
    if not stacks:
        return {}
    width, height = DEFAULT_CARD_SIZE

    if edge in ("left", "right"):
        if cards_bbox is None:
            column_x, top_y = 0.0, 0.0
        elif edge == "left":
            column_x, top_y = cards_bbox[0] - gutter - width, cards_bbox[1]
        else:
            column_x, top_y = cards_bbox[2] + gutter, cards_bbox[1]
        return {
            stack.id: (column_x, top_y + i * (height + gutter))
            for i, stack in enumerate(stacks)
        }

    if edge in ("top", "bottom"):
        if cards_bbox is None:
            left_x, row_y = 0.0, 0.0
        elif edge == "top":
            left_x, row_y = cards_bbox[0], cards_bbox[1] - gutter - height
        else:
            left_x, row_y = cards_bbox[0], cards_bbox[3] + gutter
        return {
            stack.id: (left_x + i * (width + gutter), row_y)
            for i, stack in enumerate(stacks)
        }

    raise ValueError(f"unknown edge: {edge!r}")
