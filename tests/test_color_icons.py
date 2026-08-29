from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QIcon, QImage, QPainter

from indexcards.utils.color_icons import paint_color_swatch, swatch_icon


def test_swatch_icon_returns_non_null_icon(qtbot):
    icon = swatch_icon("#FFFFFF")

    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_swatch_icon_respects_requested_size(qtbot):
    icon = swatch_icon("#FFFFFF", size=20)

    pixmap = icon.pixmap(20, 20)
    assert pixmap.width() == 20
    assert pixmap.height() == 20


def _render(hex_value: str, orphaned: bool, size: int = 20) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    try:
        paint_color_swatch(painter, QRectF(0, 0, size, size), hex_value, orphaned=orphaned)
    finally:
        painter.end()
    return image


def test_orphaned_swatch_differs_from_plain():
    plain = _render("#336699", orphaned=False)
    orphaned = _render("#336699", orphaned=True)

    assert any(
        plain.pixelColor(x, y) != orphaned.pixelColor(x, y)
        for x in range(plain.width())
        for y in range(plain.height())
    )


def test_orphaned_swatch_still_shows_base_hue_somewhere():
    image = _render("#336699", orphaned=True)
    base = QColor("#336699")

    assert any(
        image.pixelColor(x, y) == base for x in range(image.width()) for y in range(image.height())
    )


def test_non_orphaned_swatch_is_entirely_base_hue():
    image = _render("#336699", orphaned=False)
    base = QColor("#336699")

    assert all(
        image.pixelColor(x, y) == base for x in range(image.width()) for y in range(image.height())
    )


def test_swatch_icon_orphaned_vs_plain_produce_different_pixmaps():
    plain = swatch_icon("#336699", size=20).pixmap(20, 20).toImage()
    orphaned = swatch_icon("#336699", orphaned=True, size=20).pixmap(20, 20).toImage()

    assert plain != orphaned
