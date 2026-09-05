from PySide6.QtGui import QIcon

from indexcards.utils.line_weight_icons import line_weight_icon


def test_line_weight_icon_returns_non_null_icon(qtbot):
    icon = line_weight_icon(2)

    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_line_weight_icon_respects_requested_size(qtbot):
    icon = line_weight_icon(2, size=(40, 20))

    pixmap = icon.pixmap(40, 20)
    assert pixmap.width() == 40
    assert pixmap.height() == 20


def test_line_weight_icon_different_weights_produce_different_pixmaps(qtbot):
    thin = line_weight_icon(1).pixmap(28, 14).toImage()
    thick = line_weight_icon(5).pixmap(28, 14).toImage()

    assert thin != thick
