from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QIcon, QPainter, QPen, QPixmap

from indexcards.utils.arrow_geometry import arrowhead_polygon

_ICON_SIZE = (28, 14)
_LINE_COLOR = Qt.GlobalColor.darkGray
_ICON_ARROW_LENGTH = 8.0


def line_ending_icon(line_ending: str, size: tuple[int, int] = _ICON_SIZE) -> QIcon | None:
    """A small preview of a line-ending choice next to its menu label —
    mirrors swatch_icon/line_weight_icon's role for color/weight choices.
    Returns None for "none" — no symbol at all, per spec."""
    if line_ending == "none":
        return None
    width, height = size
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        y = height / 2.0
        margin = 3.0
        painter.setPen(QPen(_LINE_COLOR, 2))
        painter.drawLine(QPointF(margin, y), QPointF(width - margin, y))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_LINE_COLOR)
        if line_ending in ("to_target", "both"):
            painter.drawPolygon(
                arrowhead_polygon(QPointF(width - margin, y), QPointF(1, 0), _ICON_ARROW_LENGTH)
            )
        if line_ending in ("to_source", "both"):
            painter.drawPolygon(
                arrowhead_polygon(QPointF(margin, y), QPointF(-1, 0), _ICON_ARROW_LENGTH)
            )
    finally:
        painter.end()
    return QIcon(pixmap)
