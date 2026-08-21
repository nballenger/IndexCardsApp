from PySide6.QtCore import QEvent
from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene, QGraphicsSceneMouseEvent

from indexcards.canvas.card_item import CardItem
from indexcards.models.card import DEFAULT_CARD_SIZE, Card
from indexcards.models.document import Document


def _document_with_card() -> Document:
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="**Bold** idea", x=50.0, y=75.0))
    return document


def test_bounding_rect_matches_default_card_size():
    document = _document_with_card()
    item = CardItem("c_1", document)

    rect = item.boundingRect()
    width, height = DEFAULT_CARD_SIZE
    assert rect.width() == width
    assert rect.height() == height


def test_text_doc_renders_markdown_as_plain_text():
    document = _document_with_card()
    item = CardItem("c_1", document)

    assert item._text_doc.toPlainText() == "Bold idea"


def test_refresh_picks_up_document_text_change():
    document = _document_with_card()
    item = CardItem("c_1", document)

    document.set_card_text("c_1", "Updated *text*")
    item.refresh()

    assert item._text_doc.toPlainText() == "Updated text"


def test_without_undo_stack_item_is_not_movable():
    document = _document_with_card()
    item = CardItem("c_1", document)
    assert not (item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable)


def test_with_undo_stack_item_is_movable():
    document = _document_with_card()
    item = CardItem("c_1", document, undo_stack=QUndoStack())
    assert item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable


def _drag(item: CardItem, to_x: float, to_y: float) -> None:
    press = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMousePress)
    item.mousePressEvent(press)

    item.setPos(to_x, to_y)

    release = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMouseRelease)
    item.mouseReleaseEvent(release)


def test_drag_pushes_move_command(qtbot):
    document = _document_with_card()
    stack = QUndoStack()
    scene = QGraphicsScene()
    item = CardItem("c_1", document, undo_stack=stack)
    item.setPos(50.0, 75.0)
    scene.addItem(item)

    _drag(item, 300.0, 400.0)

    assert document.get_card("c_1").x == 300.0
    assert document.get_card("c_1").y == 400.0
    assert stack.canUndo()

    stack.undo()
    assert document.get_card("c_1").x == 50.0
    assert document.get_card("c_1").y == 75.0


def test_drag_with_no_movement_does_not_push_command(qtbot):
    document = _document_with_card()
    stack = QUndoStack()
    scene = QGraphicsScene()
    item = CardItem("c_1", document, undo_stack=stack)
    item.setPos(50.0, 75.0)
    scene.addItem(item)

    _drag(item, 50.0, 75.0)

    assert stack.canUndo() is False


def test_drag_without_undo_stack_does_not_move_document_position():
    document = _document_with_card()
    scene = QGraphicsScene()
    item = CardItem("c_1", document)
    item.setPos(50.0, 75.0)
    scene.addItem(item)

    _drag(item, 300.0, 400.0)

    assert document.get_card("c_1").x == 50.0
    assert document.get_card("c_1").y == 75.0
