from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QIcon, QPainter, QPen, QPixmap

_ICON_SIZE = (28, 14)
_LINE_COLOR = Qt.GlobalColor.darkGray
_MARGIN = 3.0


def line_weight_icon(weight: int, size: tuple[int, int] = _ICON_SIZE) -> QIcon:
    """A small horizontal line rendered at the given pen width, previewing
    a line-weight choice next to its label — mirrors swatch_icon's role
    for color choices (utils/color_icons.py)."""
    width, height = size
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(_LINE_COLOR, weight))
        y = height / 2
        painter.drawLine(QPointF(_MARGIN, y), QPointF(width - _MARGIN, y))
    finally:
        painter.end()
    return QIcon(pixmap)
