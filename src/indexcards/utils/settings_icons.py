from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

_GEAR_TOOTH_COUNT = 8
_GEAR_COLOR = "#6b6b6b"
_PAINTBRUSH_HANDLE_COLOR = "#8a5a34"
_PAINTBRUSH_FERRULE_COLOR = "#b0b0b0"
_PAINTBRUSH_BRISTLE_COLOR = "#3d6bb0"
_WARNING_TRIANGLE_COLOR = "#e0a300"
_WARNING_MARK_COLOR = "#3a2c00"


def _new_pixmap(size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    return pixmap


def gear_icon(size: int = 24) -> QIcon:
    """A filled gear: a hub circle with rotated tooth rectangles around
    it, and a punched-out center hole -- drawn procedurally like every
    other icon in this codebase (see utils/color_icons.py) rather than
    loading an asset, since the app ships none."""
    pixmap = _new_pixmap(size)
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = size / 2
        body_radius = size * 0.28
        tooth_length = size * 0.16
        tooth_width = size * 0.16
        hole_radius = size * 0.12

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(_GEAR_COLOR)))

        painter.save()
        painter.translate(center, center)
        for i in range(_GEAR_TOOTH_COUNT):
            painter.save()
            painter.rotate(360.0 / _GEAR_TOOTH_COUNT * i)
            painter.drawRect(
                QRectF(
                    -tooth_width / 2,
                    -(body_radius + tooth_length),
                    tooth_width,
                    tooth_length,
                )
            )
            painter.restore()
        painter.drawEllipse(QPointF(0, 0), body_radius, body_radius)
        painter.restore()

        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        painter.setBrush(QBrush(Qt.GlobalColor.transparent))
        painter.drawEllipse(QPointF(center, center), hole_radius, hole_radius)
    finally:
        painter.end()
    return QIcon(pixmap)


def paintbrush_icon(size: int = 24) -> QIcon:
    """A diagonal handle with a ferrule and a small color dab at the tip,
    the same procedural-QPainter idiom as gear_icon/warning_icon."""
    pixmap = _new_pixmap(size)
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        handle_width = size * 0.16
        painter.save()
        painter.translate(size * 0.66, size * 0.32)
        painter.rotate(45)
        painter.setBrush(QBrush(QColor(_PAINTBRUSH_HANDLE_COLOR)))
        painter.drawRoundedRect(
            QRectF(-handle_width / 2, -size * 0.42, handle_width, size * 0.55),
            handle_width * 0.4,
            handle_width * 0.4,
        )
        painter.restore()

        ferrule = QPainterPath()
        ferrule.moveTo(size * 0.30, size * 0.52)
        ferrule.lineTo(size * 0.58, size * 0.24)
        ferrule.lineTo(size * 0.70, size * 0.36)
        ferrule.lineTo(size * 0.42, size * 0.64)
        ferrule.closeSubpath()
        painter.setBrush(QBrush(QColor(_PAINTBRUSH_FERRULE_COLOR)))
        painter.drawPath(ferrule)

        bristle = QPainterPath()
        bristle.moveTo(size * 0.30, size * 0.52)
        bristle.lineTo(size * 0.42, size * 0.64)
        bristle.lineTo(size * 0.20, size * 0.86)
        bristle.lineTo(size * 0.14, size * 0.80)
        bristle.closeSubpath()
        painter.setBrush(QBrush(QColor(_PAINTBRUSH_BRISTLE_COLOR)))
        painter.drawPath(bristle)
    finally:
        painter.end()
    return QIcon(pixmap)


def warning_icon(size: int = 24) -> QIcon:
    """A yield-sign-style triangle with an exclamation mark built from
    primitive shapes (a rounded stem + a dot), not drawText -- keeps it
    crisp at small toolbar sizes and matches this module family's
    no-text-reliance convention."""
    pixmap = _new_pixmap(size)
    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        margin = size * 0.06
        triangle = QPainterPath()
        triangle.moveTo(size / 2, margin)
        triangle.lineTo(size - margin, size - margin)
        triangle.lineTo(margin, size - margin)
        triangle.closeSubpath()
        painter.setPen(QPen(QColor(_WARNING_MARK_COLOR), size * 0.04))
        painter.setBrush(QBrush(QColor(_WARNING_TRIANGLE_COLOR)))
        painter.drawPath(triangle)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(_WARNING_MARK_COLOR)))
        stem_width = size * 0.09
        painter.drawRoundedRect(
            QRectF(size / 2 - stem_width / 2, size * 0.38, stem_width, size * 0.28),
            stem_width * 0.4,
            stem_width * 0.4,
        )
        dot_radius = stem_width * 0.65
        painter.drawEllipse(QPointF(size / 2, size * 0.76), dot_radius, dot_radius)
    finally:
        painter.end()
    return QIcon(pixmap)
