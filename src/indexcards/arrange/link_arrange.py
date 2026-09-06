from __future__ import annotations

import math
import random

from indexcards.arrange.auto_arrange import arrange_by_tile, positions_bbox
from indexcards.models.card import DEFAULT_CARD_SIZE, Card
from indexcards.models.link import Link

FORCE_LAYOUT_ITERATIONS = 300
FORCE_LAYOUT_GUTTER = 40.0  # folded into the "ideal edge length" k below
CLUSTER_GUTTER = 60.0  # space between separately-laid-out clusters, and
# between the cluster area and the isolated-cards tile block


def _build_adjacency(card_ids: set[str], links: list[Link]) -> dict[str, set[str]]:
    """Undirected adjacency over card_ids, ignoring any link touching a
    card outside that set (a link to a pinned/stacked/off-limits card
    doesn't pull an eligible card into a "linked" component for this
    purpose -- see arrange_by_untangle_links)."""
    adjacency: dict[str, set[str]] = {card_id: set() for card_id in card_ids}
    for link in links:
        if link.source in adjacency and link.target in adjacency:
            adjacency[link.source].add(link.target)
            adjacency[link.target].add(link.source)
    return adjacency


def _walk_component(seed: str, adjacency: dict[str, set[str]]) -> list[str]:
    """Every id reachable from seed by walking adjacency, including seed
    itself -- mirrors Document.connected_card_ids, but pure (no Document)
    so it stays usable from this Qt-free module."""
    visited = {seed}
    frontier = [seed]
    component = [seed]
    while frontier:
        current = frontier.pop()
        for neighbor in adjacency.get(current, ()):
            if neighbor not in visited:
                visited.add(neighbor)
                component.append(neighbor)
                frontier.append(neighbor)
    return component


def _connected_components(card_ids: set[str], links: list[Link]) -> list[list[str]]:
    """Partitions card_ids into its connected components under the link
    graph restricted to card_ids -- a card with no live link to another
    card in card_ids comes back as its own singleton component."""
    adjacency = _build_adjacency(card_ids, links)
    visited: set[str] = set()
    components: list[list[str]] = []
    for card_id in card_ids:
        if card_id in visited:
            continue
        component = _walk_component(card_id, adjacency)
        visited.update(component)
        components.append(component)
    return components


def _fruchterman_reingold_layout(
    node_ids: list[str],
    edges: list[tuple[str, str]],
    rng: random.Random,
    iterations: int = FORCE_LAYOUT_ITERATIONS,
) -> dict[str, tuple[float, float]]:
    """Standard Fruchterman-Reingold force-directed layout: every pair of
    nodes repels (like charged particles), every edge attracts (like a
    spring), and the whole system is annealed over `iterations` steps
    with a shrinking per-step displacement cap so it settles rather than
    oscillating forever. k is the "ideal" distance between two adjacent
    nodes, sized so two connected cards' full footprints (not just their
    center points) end up clear of each other once the layout has
    converged."""
    if len(node_ids) <= 1:
        return {node_id: (0.0, 0.0) for node_id in node_ids}

    width, height = DEFAULT_CARD_SIZE
    n = len(node_ids)
    area = n * (width + FORCE_LAYOUT_GUTTER) * (height + FORCE_LAYOUT_GUTTER)
    k = math.sqrt(area / n)

    spread = k * math.sqrt(n)
    positions = {
        node_id: (rng.uniform(-spread, spread), rng.uniform(-spread, spread))
        for node_id in node_ids
    }
    temperature = spread
    cooling = temperature / iterations

    for _ in range(iterations):
        displacement = {node_id: [0.0, 0.0] for node_id in node_ids}

        for i, a in enumerate(node_ids):
            ax, ay = positions[a]
            for b in node_ids[i + 1 :]:
                bx, by = positions[b]
                dx, dy = ax - bx, ay - by
                dist = math.hypot(dx, dy) or 0.01
                force = k * k / dist
                fx, fy = dx / dist * force, dy / dist * force
                displacement[a][0] += fx
                displacement[a][1] += fy
                displacement[b][0] -= fx
                displacement[b][1] -= fy

        for source, target in edges:
            ax, ay = positions[source]
            bx, by = positions[target]
            dx, dy = ax - bx, ay - by
            dist = math.hypot(dx, dy) or 0.01
            force = dist * dist / k
            fx, fy = dx / dist * force, dy / dist * force
            displacement[source][0] -= fx
            displacement[source][1] -= fy
            displacement[target][0] += fx
            displacement[target][1] += fy

        for node_id in node_ids:
            dx, dy = displacement[node_id]
            dist = math.hypot(dx, dy) or 0.01
            capped = min(dist, temperature)
            x, y = positions[node_id]
            positions[node_id] = (x + dx / dist * capped, y + dy / dist * capped)

        temperature = max(temperature - cooling, 0.01)

    return positions


def _pack_clusters(
    cluster_layouts: list[dict[str, tuple[float, float]]],
    aspect_ratio: float,
    gutter: float,
) -> dict[str, tuple[float, float]]:
    """Places each cluster's own (already force-directed) local layout
    onto a shared canvas via simple shelf/row packing: clusters go
    left-to-right, wrapping to a new row once the current row's width
    would exceed a target width derived from aspect_ratio and the
    clusters' total area -- so a handful of small clusters end up in one
    wide row while many/large ones wrap into a roughly viewport-shaped
    block, mirroring how arrange_by_tile picks its own column count."""
    if not cluster_layouts:
        return {}
    boxes = [positions_bbox(layout) for layout in cluster_layouts]
    total_area = sum((x2 - x1) * (y2 - y1) for x1, y1, x2, y2 in boxes)
    target_row_width = math.sqrt(total_area * aspect_ratio) if total_area > 0 else 0.0

    combined: dict[str, tuple[float, float]] = {}
    cursor_x = 0.0
    cursor_y = 0.0
    row_height = 0.0
    for layout, (x1, y1, x2, y2) in zip(cluster_layouts, boxes, strict=True):
        w, h = x2 - x1, y2 - y1
        if cursor_x > 0.0 and cursor_x + w > target_row_width:
            cursor_x = 0.0
            cursor_y += row_height + gutter
            row_height = 0.0
        dx, dy = cursor_x - x1, cursor_y - y1
        for card_id, (x, y) in layout.items():
            combined[card_id] = (x + dx, y + dy)
        cursor_x += w + gutter
        row_height = max(row_height, h)
    return combined


def arrange_by_untangle_links(
    cards: list[Card],
    links: list[Link],
    aspect_ratio: float = 1.0,
    rng: random.Random | None = None,
) -> dict[str, tuple[float, float]]:
    """Groups cards into connected components via the link graph (a card
    with no live link to another card in `cards` is its own singleton,
    not a "graph"), force-directed-lays-out each real component (2+
    members) so a tangled web of links spreads out and stops
    overlapping, places those laid-out components side by side with a
    gutter between them, then tiles every isolated card into its own
    block placed to the right of them. A single global force-directed
    pass over everything wouldn't work here: an isolated card has no
    links to exert any force on it at all, so it would just sit wherever
    it happened to start."""
    if rng is None:
        rng = random.Random()
    by_id = {card.id: card for card in cards}
    components = _connected_components(set(by_id), links)
    linked_components = [c for c in components if len(c) >= 2]
    isolated_ids = [c[0] for c in components if len(c) == 1]

    cluster_layouts = []
    for component in linked_components:
        component_set = set(component)
        edges = [
            (link.source, link.target)
            for link in links
            if link.source in component_set and link.target in component_set
        ]
        cluster_layouts.append(_fruchterman_reingold_layout(component, edges, rng))

    positions = _pack_clusters(cluster_layouts, aspect_ratio, CLUSTER_GUTTER)

    if isolated_ids:
        isolated_cards = [by_id[card_id] for card_id in isolated_ids]
        tile_layout = arrange_by_tile(isolated_cards, aspect_ratio, rng)
        if positions:
            cluster_bbox = positions_bbox(positions)
            tile_bbox = positions_bbox(tile_layout)
            dx = cluster_bbox[2] + CLUSTER_GUTTER - tile_bbox[0]
            dy = cluster_bbox[1] - tile_bbox[1]
            tile_layout = {cid: (x + dx, y + dy) for cid, (x, y) in tile_layout.items()}
        positions.update(tile_layout)

    return positions


def arrange_untangle_from_card(
    seed_card_id: str,
    cards: list[Card],
    links: list[Link],
    rng: random.Random | None = None,
) -> dict[str, tuple[float, float]]:
    """Force-directed re-layout of just the connected component
    containing seed_card_id (every card reachable from it via links,
    transitively) -- everything else on the canvas is left untouched.
    The result is re-anchored to that component's own current centroid
    rather than wherever the force layout happens to converge near the
    origin, so "untangle from this card" reorganizes the cluster in
    place instead of relocating it elsewhere on the canvas. Pinned cards
    in the component are left out of the layout entirely, same as every
    other arrange action. {} if seed_card_id doesn't exist or its
    component has fewer than two unpinned members (nothing to untangle)."""
    by_id = {card.id: card for card in cards}
    if seed_card_id not in by_id:
        return {}
    adjacency = _build_adjacency(set(by_id), links)
    component = _walk_component(seed_card_id, adjacency)
    unpinned_ids = [cid for cid in component if not by_id[cid].pinned]
    if len(unpinned_ids) < 2:
        return {}

    unpinned_set = set(unpinned_ids)
    edges = [
        (link.source, link.target)
        for link in links
        if link.source in unpinned_set and link.target in unpinned_set
    ]
    local = _fruchterman_reingold_layout(unpinned_ids, edges, rng or random.Random())

    current_cx = sum(by_id[cid].x for cid in unpinned_ids) / len(unpinned_ids)
    current_cy = sum(by_id[cid].y for cid in unpinned_ids) / len(unpinned_ids)
    local_cx = sum(x for x, _y in local.values()) / len(local)
    local_cy = sum(y for _x, y in local.values()) / len(local)
    dx, dy = current_cx - local_cx, current_cy - local_cy
    return {cid: (x + dx, y + dy) for cid, (x, y) in local.items()}
