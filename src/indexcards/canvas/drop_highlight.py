from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QGraphicsItem, QGraphicsRectItem

from indexcards.utils.contrast import auto_text_color, contrast_ratio

_HALO_COLOR = QColor("#16ffff")
_HALO_BLUR_RADIUS = 24.0
_MIN_CONTRAST = 3.0  # WCAG's non-text/graphical-object minimum
_RING_MARGIN = 3.0  # gap between the target's own edge and the ring
_RING_WIDTH = 3.0  # thickness of the solid color band itself
_RING_Z_EPSILON = 0.5  # keeps the ring just below the dragged item (see below)

# Keyed by the highlighted CardItem/StackItem itself, not a per-item bool
# attribute -- keeps every bit of new state contained in this module
# rather than reaching into CardItem/StackItem to add one.
_active_rings: dict[QGraphicsItem, QGraphicsRectItem] = {}


def is_drop_highlighted(item: QGraphicsItem) -> bool:
    return item in _active_rings


def apply_drop_highlight(
    item: QGraphicsItem,
    highlighted: bool,
    background_hex: str = "",
    dragged_item: QGraphicsItem | None = None,
) -> None:
    """Toggles the highlight shown on a card/stack that's currently a
    valid live-drag drop target (see CardItem/StackItem's own
    mouseMoveEvent overrides) — shared since the visual is identical
    regardless of which class the target is.

    A blurred drop shadow alone, at any color or blur radius, proved too
    subtle in practice (confirmed live, not just in theory) — a thin
    edge doesn't give the blur enough of a silhouette to read as bold.
    Instead this wraps the target in a genuinely solid colored band — a
    separate sibling QGraphicsRectItem added to (and removed from) the
    same scene, rather than a wider CardItem/StackItem.boundingRect():
    that rect also drives the drop-zone/quartile hit-testing math
    elsewhere, so enlarging it would silently change *drop behavior*,
    not just appearance — and applies the same soft drop shadow *around*
    that band, so the blur has a bold, opaque shape to diffuse from.

    background_hex is the current canvas background color: if the fixed
    amber's contrast against it falls below _MIN_CONTRAST, falls back to
    auto_text_color(background_hex) (pure black or white, whichever
    contrasts more — the same function already used to pick card text
    color) instead, so the highlight is never invisible against a
    background close to its own hue. Only read when highlighted=True.

    dragged_item is whatever's currently being dragged (the card/stack
    calling this on its own live target, i.e. its own "self") — the ring
    is placed just *below* it in z-order, so the item actually being
    moved always stays visibly on top instead of disappearing under the
    ring's frame the moment it crosses into the trigger zone.
    CanvasScene.bring_item_to_front() raises whatever's pressed to a
    fresh, strictly-higher z-value than anything else on a single-item
    drag (the only kind that ever highlights anything), so dragged_item's
    z-value is guaranteed above the target's — placing the ring at
    dragged_item's z minus a small epsilon reliably sits it between the
    two. Falls back to just above the target's own z-value (the old
    behavior, minus the large constant) when not given."""
    if highlighted == is_drop_highlighted(item):
        return
    if highlighted:
        scene = item.scene()
        if scene is None:
            return
        color = _HALO_COLOR
        if contrast_ratio(_HALO_COLOR.name(), background_hex) < _MIN_CONTRAST:
            color = QColor(auto_text_color(background_hex))
        ring_rect = item.mapRectToScene(item.boundingRect()).adjusted(
            -_RING_MARGIN, -_RING_MARGIN, _RING_MARGIN, _RING_MARGIN
        )
        ring = QGraphicsRectItem(ring_rect)
        ring.setPen(QPen(color, _RING_WIDTH))
        ring.setBrush(Qt.BrushStyle.NoBrush)
        if dragged_item is not None:
            ring.setZValue(dragged_item.zValue() - _RING_Z_EPSILON)
        else:
            ring.setZValue(item.zValue() + _RING_Z_EPSILON)
        effect = QGraphicsDropShadowEffect()
        effect.setColor(color)
        effect.setOffset(0, 0)
        effect.setBlurRadius(_HALO_BLUR_RADIUS)
        ring.setGraphicsEffect(effect)
        scene.addItem(ring)
        _active_rings[item] = ring
    else:
        ring = _active_rings.pop(item)
        ring_scene = ring.scene()
        if ring_scene is not None:
            ring_scene.removeItem(ring)
