from __future__ import annotations

import math
import random

from indexcards.models.card import DEFAULT_CARD_SIZE, Card
from indexcards.models.palette import PALETTE

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
    """One stack per distinct color present, ordered by hex value for stable output."""
    groups: dict[str, list[Card]] = {}
    for card in cards:
        groups.setdefault(card.color, []).append(card)

    positions: dict[str, tuple[float, float]] = {}
    for i, color in enumerate(sorted(groups)):
        positions.update(_cascade_positions(groups[color], i * STACK_SPACING_X))
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


def _color_category_order(colors: set[str]) -> list[str]:
    """Palette colors first, in the palette's own defined order (matching
    the card color-picker's swatch order) — then any non-palette color
    (e.g. from hand-edited or legacy data) sorted by hex value after."""
    palette_hexes = list(PALETTE.values())
    known = [color for color in palette_hexes if color in colors]
    unknown = sorted(color for color in colors if color not in palette_hexes)
    return known + unknown


def arrange_by_columns_color(
    cards: list[Card], overflow_limit: int | None = None
) -> dict[str, tuple[float, float]]:
    """One column-group per distinct color, ordered per _color_category_order;
    within each, cards sort alphabetically (case sensitive) by text."""
    groups: dict[str, list[Card]] = {}
    for card in cards:
        groups.setdefault(card.color, []).append(card)

    categories = [
        sorted(groups[color], key=lambda card: card.text)
        for color in _color_category_order(set(groups))
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
        return arrange_by_columns_color(cards, overflow_limit)
    if group_by == "columns_alphabetical":
        return arrange_by_columns_alphabetical(cards, overflow_limit)
    raise ValueError(f"unknown group_by: {group_by!r}")


PINNED_AVOIDANCE_GUTTER = 40.0


def _positions_bbox(
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


def arrange_avoiding_pinned(
    cards: list[Card],
    group_by: str,
    tag: str | None = None,
    aspect_ratio: float = 1.0,
    overflow_limit: int | None = None,
) -> dict[str, tuple[float, float]]:
    """Like auto_arrange_positions, but leaves every pinned card exactly
    where it is and only repositions the rest — shifting the freshly
    computed layout for the unpinned cards (preserving its internal
    arrangement) just far enough to clear the pinned cards' bounding box,
    if it would otherwise overlap it. Returns positions only for the
    cards that actually moved (pinned card ids aren't included), or {} if
    every card is pinned."""
    pinned = [card for card in cards if card.pinned]
    unpinned = [card for card in cards if not card.pinned]
    if not unpinned:
        return {}

    new_positions = auto_arrange_positions(
        unpinned, group_by, tag, aspect_ratio=aspect_ratio, overflow_limit=overflow_limit
    )
    if not pinned:
        return new_positions

    pinned_bbox = _positions_bbox({card.id: (card.x, card.y) for card in pinned})
    new_bbox = _positions_bbox(new_positions)
    dx, dy = _shift_to_clear_overlap(new_bbox, pinned_bbox, PINNED_AVOIDANCE_GUTTER)
    if dx == 0.0 and dy == 0.0:
        return new_positions
    return {card_id: (x + dx, y + dy) for card_id, (x, y) in new_positions.items()}
