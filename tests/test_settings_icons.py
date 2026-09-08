from PySide6.QtGui import QIcon

from indexcards.utils.settings_icons import gear_icon, paintbrush_icon, warning_icon


def test_gear_icon_returns_non_null_icon(qtbot):
    icon = gear_icon()

    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_paintbrush_icon_returns_non_null_icon(qtbot):
    icon = paintbrush_icon()

    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_warning_icon_returns_non_null_icon(qtbot):
    icon = warning_icon()

    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_icons_respect_requested_size(qtbot):
    for icon_fn in (gear_icon, paintbrush_icon, warning_icon):
        pixmap = icon_fn(size=32).pixmap(32, 32)
        assert pixmap.width() == 32
        assert pixmap.height() == 32


def test_the_three_icons_produce_different_pixmaps(qtbot):
    gear = gear_icon(size=24).pixmap(24, 24).toImage()
    paintbrush = paintbrush_icon(size=24).pixmap(24, 24).toImage()
    warning = warning_icon(size=24).pixmap(24, 24).toImage()

    assert gear != paintbrush
    assert gear != warning
    assert paintbrush != warning
