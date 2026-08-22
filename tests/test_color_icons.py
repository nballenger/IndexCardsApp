from PySide6.QtGui import QIcon

from indexcards.utils.color_icons import swatch_icon


def test_swatch_icon_returns_non_null_icon(qtbot):
    icon = swatch_icon("#FFFFFF")

    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_swatch_icon_respects_requested_size(qtbot):
    icon = swatch_icon("#FFFFFF", size=20)

    pixmap = icon.pixmap(20, 20)
    assert pixmap.width() == 20
    assert pixmap.height() == 20
