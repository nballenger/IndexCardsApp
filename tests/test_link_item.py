from PySide6.QtCore import QPointF

from indexcards.canvas.card_item import CardItem
from indexcards.canvas.link_item import LinkItem
from indexcards.models.card import DEFAULT_CARD_SIZE, Card
from indexcards.models.document import Document

_WIDTH, _HEIGHT = DEFAULT_CARD_SIZE
_CENTER_OFFSET = QPointF(_WIDTH / 2, _HEIGHT / 2)


def _document_with_two_cards() -> Document:
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    document.add_card(Card(id="c_2", x=300.0, y=0.0))
    return document


def test_link_item_line_starts_at_card_centers(qtbot):
    document = _document_with_two_cards()
    item1 = CardItem("c_1", document)
    item1.setPos(0.0, 0.0)
    item2 = CardItem("c_2", document)
    item2.setPos(300.0, 0.0)

    link = LinkItem("l_1", item1, item2)

    line = link.line()
    assert line.p1() == QPointF(0, 0) + _CENTER_OFFSET
    assert line.p2() == QPointF(300, 0) + _CENTER_OFFSET


def test_link_item_line_follows_card_move(qtbot):
    document = _document_with_two_cards()
    item1 = CardItem("c_1", document)
    item1.setPos(0.0, 0.0)
    item2 = CardItem("c_2", document)
    item2.setPos(300.0, 0.0)
    link = LinkItem("l_1", item1, item2)

    item1.setPos(500.0, 600.0)

    line = link.line()
    assert line.p1() == QPointF(500, 600) + _CENTER_OFFSET
    assert line.p2() == QPointF(300, 0) + _CENTER_OFFSET


def test_disconnect_listeners_stops_line_from_following(qtbot):
    document = _document_with_two_cards()
    item1 = CardItem("c_1", document)
    item1.setPos(0.0, 0.0)
    item2 = CardItem("c_2", document)
    item2.setPos(300.0, 0.0)
    link = LinkItem("l_1", item1, item2)

    link.disconnect_listeners()
    item1.setPos(999.0, 999.0)

    line = link.line()
    assert line.p1() == QPointF(0, 0) + _CENTER_OFFSET


def test_set_dimmed_changes_pen(qtbot):
    document = _document_with_two_cards()
    item1 = CardItem("c_1", document)
    item2 = CardItem("c_2", document)
    link = LinkItem("l_1", item1, item2)
    normal_pen = link.pen()

    link.set_dimmed(True)
    dimmed_pen = link.pen()
    assert dimmed_pen.color() != normal_pen.color()

    link.set_dimmed(False)
    assert link.pen().color() == normal_pen.color()
