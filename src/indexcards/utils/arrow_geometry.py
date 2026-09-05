from __future__ import annotations

import math

from PySide6.QtCore import QPointF
from PySide6.QtGui import QPolygonF

ARROW_LENGTH = 14.0
_ARROW_ANGLE_DEGREES = 25.0


def arrowhead_half_width(length: float = ARROW_LENGTH) -> float:
    return length * math.tan(math.radians(_ARROW_ANGLE_DEGREES))


def arrowhead_polygon(tip: QPointF, direction: QPointF, length: float = ARROW_LENGTH) -> QPolygonF:
    """A solid triangular arrowhead (tip, left wing, right wing) at tip,
    pointing along direction (need not be normalized) — shared by
    LinkItem's real on-canvas rendering and the small menu-icon preview,
    so both draw the identical shape."""
    magnitude = math.hypot(direction.x(), direction.y())
    if magnitude == 0:
        return QPolygonF([tip, tip, tip])
    ux, uy = direction.x() / magnitude, direction.y() / magnitude
    px, py = -uy, ux
    back = QPointF(tip.x() - ux * length, tip.y() - uy * length)
    half_width = arrowhead_half_width(length)
    left = QPointF(back.x() + px * half_width, back.y() + py * half_width)
    right = QPointF(back.x() - px * half_width, back.y() - py * half_width)
    return QPolygonF([tip, left, right])
