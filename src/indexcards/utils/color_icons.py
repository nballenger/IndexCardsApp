from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

_SWATCH_SIZE = 14


def swatch_icon(hex_value: str, size: int = _SWATCH_SIZE) -> QIcon:
    """A small solid-color square icon previewing a color choice next to
    its name — used by every color picker (list-view combo, canvas
    right-click menu) so the palette's colors don't have to be
    memorized by name."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(hex_value))
        painter.setPen(Qt.GlobalColor.darkGray)
        painter.drawRect(1, 1, size - 2, size - 2)
    finally:
        painter.end()
    return QIcon(pixmap)
