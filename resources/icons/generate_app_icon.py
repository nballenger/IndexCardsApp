"""Generates the master 1024x1024 app icon PNG (resources/icons/app_icon.png),
which build_icns.sh then converts into the .icns bundled by PyInstaller.

Drawn procedurally with QPainter -- same idiom as the app's own runtime icon
modules (utils/color_icons.py, utils/settings_icons.py) -- rather than a
binary asset authored in external design tools, so the icon can be
regenerated/tweaked by editing this file. Uses the Classic preset theme's own
palette (models/presets.py) so the icon reads as authentically part of the
app rather than a generic stock image: the felt-table green background and
three of its pastel card colors, fanned like a small stack of index cards.

Run with: uv run python resources/icons/generate_app_icon.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QApplication

_SIZE = 1024
_OUTPUT_PATH = Path(__file__).parent / "app_icon.png"

_BACKGROUND_COLOR = "#3d6b4f"  # Classic preset's canvas background
_CARD_COLORS = ("#D6C6F0", "#A8D8F0", "#F6E27A")  # Classic preset: Purple, Blue, Yellow


def _draw_card(
    painter: QPainter,
    center: QPointF,
    angle_deg: float,
    width: float,
    height: float,
    fill_hex: str,
) -> None:
    painter.save()
    painter.translate(center)
    painter.rotate(angle_deg)
    rect = QRectF(-width / 2, -height / 2, width, height)

    shadow_path = QPainterPath()
    shadow_path.addRect(rect.translated(_SIZE * 0.012, _SIZE * 0.02))
    painter.fillPath(shadow_path, QColor(0, 0, 0, 60))

    card_path = QPainterPath()
    card_path.addRect(rect)  # sharp corners, matching a real index card
    painter.fillPath(card_path, QColor(fill_hex))
    border_color = QColor("#000000")
    border_color.setAlpha(34)
    painter.setPen(QPen(border_color, _SIZE * 0.003))
    painter.drawPath(card_path)

    line_color = QColor("#000000")
    line_color.setAlpha(90)
    pen = QPen(line_color)
    pen.setWidthF(_SIZE * 0.010)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    line_inset_x = width * 0.16
    for index, fraction in enumerate((0.30, 0.50, 0.70)):
        y = rect.top() + height * fraction
        shrink = width * 0.18 if index == 2 else 0.0  # last line a bit shorter, less mechanical
        painter.drawLine(
            QPointF(rect.left() + line_inset_x, y), QPointF(rect.right() - line_inset_x - shrink, y)
        )
    painter.restore()


def generate() -> Path:
    app = QApplication.instance() or QApplication(sys.argv)
    pixmap = QPixmap(_SIZE, _SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    background_rect = QRectF(0, 0, _SIZE, _SIZE)
    background_path = QPainterPath()
    background_path.addRoundedRect(background_rect, _SIZE * 0.22, _SIZE * 0.22)
    painter.fillPath(background_path, QColor(_BACKGROUND_COLOR))
    gradient = QRadialGradient(_SIZE / 2, _SIZE * 0.42, _SIZE * 0.75)
    gradient.setColorAt(0.0, QColor(255, 255, 255, 18))
    gradient.setColorAt(1.0, QColor(0, 0, 0, 40))
    painter.fillPath(background_path, QBrush(gradient))

    card_width, card_height = _SIZE * 0.65, _SIZE * 0.40
    center = QPointF(_SIZE / 2, _SIZE / 2 + _SIZE * 0.02)
    fan = (
        (QPointF(-_SIZE * 0.0425, _SIZE * 0.0125), -10),
        (QPointF(_SIZE * 0.034, _SIZE * 0.0045), 8),
        (QPointF(0, 0), 0),
    )
    for (offset, angle), color in zip(fan, _CARD_COLORS, strict=True):
        _draw_card(painter, center + offset, angle, card_width, card_height, color)

    painter.end()
    pixmap.save(str(_OUTPUT_PATH))
    del app
    return _OUTPUT_PATH


if __name__ == "__main__":
    path = generate()
    print(f"Saved {path}")
