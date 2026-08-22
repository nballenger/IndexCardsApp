from PySide6.QtCore import QRect
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QStyleOptionViewItem

from indexcards.list_view.color_delegate import ColorDelegate

_SWATCH_WIDTH = 16


class _FakeModel:
    def __init__(self, hex_value: str) -> None:
        self._hex_value = hex_value

    def data(self, index, role):
        return self._hex_value


class _FakeIndex:
    def __init__(self, model: _FakeModel) -> None:
        self._model = model

    def model(self) -> _FakeModel:
        return self._model


def _paint_and_capture_swatch(width: int, height: int, monkeypatch) -> QRect:
    captured = []
    monkeypatch.setattr(QPainter, "drawRect", lambda self, rect: captured.append(rect))

    delegate = ColorDelegate()
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, width, height)
    index = _FakeIndex(_FakeModel("#FFFFFF"))

    image = QImage(max(width, 1), max(height, 1), QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        delegate.paint(painter, option, index)
    finally:
        painter.end()

    return captured[0]


def test_swatch_is_horizontally_centered(monkeypatch):
    swatch = _paint_and_capture_swatch(100, 30, monkeypatch)

    expected_left = (100 - _SWATCH_WIDTH) // 2
    assert swatch.left() == expected_left
    assert swatch.width() == _SWATCH_WIDTH


def test_swatch_stays_centered_in_a_wider_column(monkeypatch):
    swatch = _paint_and_capture_swatch(200, 30, monkeypatch)

    expected_left = (200 - _SWATCH_WIDTH) // 2
    assert swatch.left() == expected_left
