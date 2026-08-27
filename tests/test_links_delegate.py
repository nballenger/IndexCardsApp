from PySide6.QtCore import QRect
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QStyleOptionViewItem

from indexcards.list_view.card_table_model import LINKS_ROLE
from indexcards.list_view.links_delegate import LinksDelegate


class _FakeModel:
    def __init__(self, links: list[tuple[str, str]]) -> None:
        self._links = links

    def data(self, index, role):
        if role == LINKS_ROLE:
            return self._links
        return None


class _FakeIndex:
    def __init__(self, model: _FakeModel) -> None:
        self._model = model

    def data(self, role):
        return self._model.data(self, role)


def _option(rect: QRect) -> QStyleOptionViewItem:
    option = QStyleOptionViewItem()
    option.rect = rect
    return option


def test_segments_lays_out_ids_left_to_right_with_a_gap_between():
    delegate = LinksDelegate()
    index = _FakeIndex(_FakeModel([("c_2", "second"), ("c_3", "third")]))
    option = _option(QRect(0, 0, 200, 20))

    segments = delegate.segments(option, index)

    assert [card_id for card_id, _text, _rect in segments] == ["c_2", "c_3"]
    first_rect, second_rect = segments[0][2], segments[1][2]
    assert second_rect.left() > first_rect.right()


def test_segments_empty_when_no_links():
    delegate = LinksDelegate()
    index = _FakeIndex(_FakeModel([]))
    assert delegate.segments(_option(QRect(0, 0, 200, 20)), index) == []


def test_segment_at_hit_tests_the_containing_segment():
    delegate = LinksDelegate()
    index = _FakeIndex(_FakeModel([("c_2", "second"), ("c_3", "third")]))
    option = _option(QRect(0, 0, 200, 20))
    segments = delegate.segments(option, index)

    assert delegate.segment_at(option, index, segments[0][2].center()) == 0
    assert delegate.segment_at(option, index, segments[1][2].center()) == 1
    assert delegate.segment_at(option, index, option.rect.bottomRight()) == -1


def test_paint_underlines_only_the_hovered_segment(monkeypatch):
    drawn = []
    monkeypatch.setattr(
        QPainter,
        "drawText",
        lambda self, rect, flags, text: drawn.append((text, self.font().underline())),
    )

    delegate = LinksDelegate()
    index = _FakeIndex(_FakeModel([("c_2", "second"), ("c_3", "third")]))
    delegate.hovered_index = index
    delegate.hovered_segment = 1

    option = _option(QRect(0, 0, 200, 20))
    image = QImage(200, 20, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        delegate.paint(painter, option, index)
    finally:
        painter.end()

    underline_by_text = dict(drawn)
    assert underline_by_text["c_2"] is False
    assert underline_by_text["c_3"] is True
    assert underline_by_text[", "] is False


def test_paint_underlines_nothing_when_not_hovered(monkeypatch):
    drawn = []
    monkeypatch.setattr(
        QPainter,
        "drawText",
        lambda self, rect, flags, text: drawn.append((text, self.font().underline())),
    )

    delegate = LinksDelegate()
    index = _FakeIndex(_FakeModel([("c_2", "second")]))

    option = _option(QRect(0, 0, 200, 20))
    image = QImage(200, 20, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        delegate.paint(painter, option, index)
    finally:
        painter.end()

    assert dict(drawn)["c_2"] is False
