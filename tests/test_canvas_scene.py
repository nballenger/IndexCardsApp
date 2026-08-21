from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import QGraphicsItem

from indexcards.canvas.canvas_scene import CanvasScene
from indexcards.models.card import Card
from indexcards.models.document import Document


def _document_with_cards() -> Document:
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="first", x=10.0, y=20.0))
    document.add_card(Card(id="c_2", text="second", x=200.0, y=300.0))
    return document


def test_scene_creates_items_at_stored_positions():
    document = _document_with_cards()
    scene = CanvasScene(document)

    item1 = scene.item_for_card("c_1")
    item2 = scene.item_for_card("c_2")
    assert item1 is not None
    assert item2 is not None
    assert (item1.pos().x(), item1.pos().y()) == (10.0, 20.0)
    assert (item2.pos().x(), item2.pos().y()) == (200.0, 300.0)
    assert len(scene.items()) == 2


def test_scene_adds_item_on_card_added():
    document = _document_with_cards()
    scene = CanvasScene(document)

    document.add_card(Card(id="c_3", text="third", x=1.0, y=2.0))

    item = scene.item_for_card("c_3")
    assert item is not None
    assert (item.pos().x(), item.pos().y()) == (1.0, 2.0)


def test_scene_removes_item_on_card_removed():
    document = _document_with_cards()
    scene = CanvasScene(document)

    document.remove_card("c_1")

    assert scene.item_for_card("c_1") is None
    assert len(scene.items()) == 1


def test_scene_refreshes_item_on_card_changed():
    document = _document_with_cards()
    scene = CanvasScene(document)

    document.set_card_text("c_1", "updated text")

    item = scene.item_for_card("c_1")
    assert item._text_doc.toPlainText() == "updated text"


def test_scene_repositions_item_on_card_moved():
    document = _document_with_cards()
    scene = CanvasScene(document)

    document.set_card_position("c_1", 500.0, 600.0)

    item = scene.item_for_card("c_1")
    assert (item.pos().x(), item.pos().y()) == (500.0, 600.0)


def test_scene_passes_undo_stack_to_items_making_them_movable():
    document = _document_with_cards()
    stack = QUndoStack()
    scene = CanvasScene(document, undo_stack=stack)

    item = scene.item_for_card("c_1")
    assert item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable


def test_scene_without_undo_stack_items_are_not_movable():
    document = _document_with_cards()
    scene = CanvasScene(document)

    item = scene.item_for_card("c_1")
    assert not (item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable)


def test_scene_repositions_items_on_bulk_move():
    document = _document_with_cards()
    scene = CanvasScene(document)

    document.bulk_set_positions({"c_1": (11.0, 22.0), "c_2": (33.0, 44.0)})

    assert (scene.item_for_card("c_1").pos().x(), scene.item_for_card("c_1").pos().y()) == (
        11.0,
        22.0,
    )
    assert (scene.item_for_card("c_2").pos().x(), scene.item_for_card("c_2").pos().y()) == (
        33.0,
        44.0,
    )
