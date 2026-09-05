from PySide6.QtGui import QIcon

from indexcards.utils.line_ending_icons import line_ending_icon


def test_none_returns_no_icon():
    assert line_ending_icon("none") is None


def test_to_target_returns_non_null_icon():
    icon = line_ending_icon("to_target")
    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_to_source_returns_non_null_icon():
    icon = line_ending_icon("to_source")
    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_both_returns_non_null_icon():
    icon = line_ending_icon("both")
    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_different_states_produce_different_pixmaps():
    to_target = line_ending_icon("to_target").pixmap(28, 14).toImage()
    to_source = line_ending_icon("to_source").pixmap(28, 14).toImage()
    both = line_ending_icon("both").pixmap(28, 14).toImage()

    assert to_target != to_source
    assert to_target != both
    assert to_source != both


def test_respects_requested_size():
    icon = line_ending_icon("both", size=(40, 20))

    pixmap = icon.pixmap(40, 20)
    assert pixmap.width() == 40
    assert pixmap.height() == 20
