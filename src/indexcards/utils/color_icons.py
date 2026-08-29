from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

from indexcards.utils.contrast import auto_text_color

_SWATCH_SIZE = 14
_HATCH_SPACING = 6.0
_HATCH_WIDTH = 1.5
_HATCH_ALPHA = 70


def paint_color_swatch(
    painter: QPainter, rect: QRectF, hex_value: str, orphaned: bool = False
) -> None:
    """Fills rect with hex_value and, if orphaned, overlays light 45°
    diagonal hatching in whichever of black/white contrasts against
    hex_value (auto_text_color) — so the hatch is always visible
    regardless of hue, while the base color still shows through between
    lines, keeping different orphaned colors distinguishable from each
    other (hatching is a shared "orphaned" texture, not a hue-encoding
    device). Draws fill only — no border/pen — so callers with different
    border needs (a plain menu-icon border vs. CardItem's own selection-
    dependent border) can layer their own stroke on top."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.fillRect(rect, QColor(hex_value))
    if orphaned:
        hatch_color = QColor(auto_text_color(hex_value))
        hatch_color.setAlpha(_HATCH_ALPHA)
        painter.setPen(QPen(hatch_color, _HATCH_WIDTH))
        painter.setClipRect(rect)
        span = (rect.width() + rect.height()) or 1.0
        offset = -span
        while offset < span:
            painter.drawLine(
                QPointF(rect.left() + offset, rect.bottom()),
                QPointF(rect.left() + offset + rect.height(), rect.top()),
            )
            offset += _HATCH_SPACING
    painter.restore()


def swatch_icon(hex_value: str, orphaned: bool = False, size: int = _SWATCH_SIZE) -> QIcon:
    """A small solid-color square icon previewing a color choice next to
    its name — used by every color picker (list-view combo, canvas
    right-click menu) so the theme's colors don't have to be memorized by
    name."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        rect = QRectF(1, 1, size - 2, size - 2)
        paint_color_swatch(painter, rect, hex_value, orphaned)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.GlobalColor.darkGray)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(rect)
    finally:
        painter.end()
    return QIcon(pixmap)
