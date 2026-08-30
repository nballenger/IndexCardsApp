from PySide6.QtCore import QEvent
from PySide6.QtGui import QImage, QPainter, QUndoStack
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene, QGraphicsSceneMouseEvent, QMessageBox

from indexcards.canvas.stack_item import StackItem
from indexcards.commands.stack_commands import ExplodeStackCommand
from indexcards.models.card import DEFAULT_CARD_SIZE, Card
from indexcards.models.document import Document
from indexcards.models.stack import Stack


def _document_with_stack(**stack_kwargs) -> Document:
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0, stack_id="s_1"))
    document.add_card(Card(id="c_2", x=0.0, y=0.0, stack_id="s_1"))
    document.add_stack(Stack(id="s_1", card_ids=["c_1", "c_2"], x=0.0, y=0.0, **stack_kwargs))
    return document


def test_bounding_rect_is_card_size_plus_depth():
    document = _document_with_stack()
    item = StackItem("s_1", document)

    width, height = DEFAULT_CARD_SIZE
    rect = item.boundingRect()
    assert rect.width() > width
    assert rect.height() > height


def test_paint_does_not_crash():
    document = _document_with_stack(label="Chapter 1")
    item = StackItem("s_1", document)

    image = QImage(300, 300, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        item.paint(painter, None)
    finally:
        painter.end()


def test_without_undo_stack_item_is_not_movable():
    document = _document_with_stack()
    item = StackItem("s_1", document)
    assert not (item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable)


def test_with_undo_stack_item_is_movable():
    document = _document_with_stack()
    item = StackItem("s_1", document, undo_stack=QUndoStack())
    assert item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable


def _drag(item: StackItem, to_x: float, to_y: float) -> None:
    press = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMousePress)
    item.mousePressEvent(press)

    item.setPos(to_x, to_y)

    release = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMouseRelease)
    item.mouseReleaseEvent(release)


def test_drag_pushes_move_stack_command():
    document = _document_with_stack()
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    item = StackItem("s_1", document, undo_stack=undo_stack)
    scene.addItem(item)

    _drag(item, 300.0, 400.0)

    assert (document.get_stack("s_1").x, document.get_stack("s_1").y) == (300.0, 400.0)
    assert undo_stack.canUndo()

    undo_stack.undo()
    assert (document.get_stack("s_1").x, document.get_stack("s_1").y) == (0.0, 0.0)


def test_drag_with_no_movement_does_not_push_command():
    document = _document_with_stack()
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    item = StackItem("s_1", document, undo_stack=undo_stack)
    scene.addItem(item)

    _drag(item, 0.0, 0.0)

    assert undo_stack.canUndo() is False


def test_double_click_without_view_does_not_crash():
    document = _document_with_stack()
    scene = QGraphicsScene()
    item = StackItem("s_1", document, undo_stack=QUndoStack())
    scene.addItem(item)

    press = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMouseDoubleClick)
    item.mouseDoubleClickEvent(press)  # scene has no attached QGraphicsView — must not raise


def test_build_context_menu_shows_label_when_unlabeled():
    document = _document_with_stack()
    item = StackItem("s_1", document, undo_stack=QUndoStack())

    _menu, _delete, _tile, _scatter, label_action = item._build_context_menu()

    assert label_action.text() == "Label"


def test_build_context_menu_shows_change_label_when_labeled():
    document = _document_with_stack(label="Chapter 1")
    item = StackItem("s_1", document, undo_stack=QUndoStack())

    _menu, _delete, _tile, _scatter, label_action = item._build_context_menu()

    assert label_action.text() == "Change Label"


def test_delete_via_dialog_confirmed_removes_stack_and_cards(monkeypatch):
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.Yes)
    document = _document_with_stack()
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    item = StackItem("s_1", document, undo_stack=undo_stack)
    scene.addItem(item)

    item._delete_via_dialog()

    assert "s_1" not in document.stacks
    assert document.cards == {}


def test_delete_via_dialog_cancelled_leaves_stack_intact(monkeypatch):
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.Cancel)
    document = _document_with_stack()
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    item = StackItem("s_1", document, undo_stack=undo_stack)
    scene.addItem(item)

    item._delete_via_dialog()

    assert "s_1" in document.stacks
    assert undo_stack.canUndo() is False


def test_explode_pushes_explode_command_and_fits_view(qtbot):
    from indexcards.canvas.canvas_view import CanvasView

    document = _document_with_stack()
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    view = CanvasView()
    view.setScene(scene)
    qtbot.addWidget(view)
    item = StackItem("s_1", document, undo_stack=undo_stack)
    scene.addItem(item)

    item._explode("tile")

    assert "s_1" not in document.stacks
    assert document.get_card("c_1").stack_id is None
    assert document.get_card("c_2").stack_id is None
    assert isinstance(undo_stack.command(undo_stack.index() - 1), ExplodeStackCommand)


def test_edit_label_via_dialog_pushes_change_label_command(monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("New Label", True))
    document = _document_with_stack()
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    item = StackItem("s_1", document, undo_stack=undo_stack)
    scene.addItem(item)

    item._edit_label_via_dialog()

    assert document.get_stack("s_1").label == "New Label"


def test_edit_label_via_dialog_cancelled_does_nothing(monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("New Label", False))
    document = _document_with_stack()
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    item = StackItem("s_1", document, undo_stack=undo_stack)
    scene.addItem(item)

    item._edit_label_via_dialog()

    assert document.get_stack("s_1").label == ""
    assert undo_stack.canUndo() is False
