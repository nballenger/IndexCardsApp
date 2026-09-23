from PySide6.QtCore import QEvent, QPointF
from PySide6.QtGui import QImage, QPainter, QUndoStack
from PySide6.QtWidgets import QGraphicsScene, QGraphicsSceneMouseEvent

from indexcards.canvas import region_item as region_item_module
from indexcards.canvas.card_item import CardItem
from indexcards.canvas.region_item import RegionItem
from indexcards.canvas.stack_item import StackItem
from indexcards.commands.region_commands import RemoveRegionCommand
from indexcards.models.card import Card
from indexcards.models.document import Document
from indexcards.models.region import MIN_REGION_SIZE, Region
from indexcards.models.stack import Stack


def _document_with_region(**region_kwargs) -> Document:
    document = Document(name="Test")
    kwargs = {"x": 0.0, "y": 0.0, "width": 300.0, "height": 200.0, **region_kwargs}
    document.add_region(Region(id="r_1", **kwargs))
    return document


def _mouse_event(kind, local_pos: QPointF, scene_pos: QPointF) -> QGraphicsSceneMouseEvent:
    event = QGraphicsSceneMouseEvent(kind)
    event.setPos(local_pos)
    event.setScenePos(scene_pos)
    return event


def _press(pos: QPointF) -> QGraphicsSceneMouseEvent:
    return _mouse_event(QEvent.Type.GraphicsSceneMousePress, pos, pos)


def _move(pos: QPointF) -> QGraphicsSceneMouseEvent:
    return _mouse_event(QEvent.Type.GraphicsSceneMouseMove, pos, pos)


def _release(pos: QPointF) -> QGraphicsSceneMouseEvent:
    return _mouse_event(QEvent.Type.GraphicsSceneMouseRelease, pos, pos)


def test_paint_does_not_crash():
    document = _document_with_region(label="Open Questions")
    item = RegionItem("r_1", document)

    image = QImage(400, 300, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        item.paint(painter, None, None)
    finally:
        painter.end()


def test_paint_draws_a_solid_opaque_title_bar_even_without_a_label():
    document = _document_with_region()  # no label set
    item = RegionItem("r_1", document)

    image = QImage(400, 300, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    try:
        item.paint(painter, None, None)
    finally:
        painter.end()

    title_bar_pixel = image.pixelColor(10, 10)  # inside the label bar strip
    body_pixel = image.pixelColor(10, 100)  # inside the region body

    assert title_bar_pixel.alpha() == 255  # opaque, matching the solid border color
    assert body_pixel.alpha() < 255  # the body stays a translucent tint
    assert title_bar_pixel != body_pixel


def test_paint_after_region_removed_does_not_crash():
    document = _document_with_region()
    item = RegionItem("r_1", document)
    document.remove_region("r_1")

    image = QImage(400, 300, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        item.paint(painter, None, None)
    finally:
        painter.end()


def test_zone_at_label_bar_is_move():
    document = _document_with_region()
    item = RegionItem("r_1", document)

    assert item._zone_at(QPointF(10, 10)) == "move"


def test_zone_at_body_is_none():
    document = _document_with_region()
    item = RegionItem("r_1", document)

    assert item._zone_at(QPointF(150, 100)) is None


def test_zone_at_border_band_is_resize():
    document = _document_with_region()
    item = RegionItem("r_1", document)

    assert item._zone_at(QPointF(2, 100)) == "resize"
    assert item._zone_at(QPointF(298, 100)) == "resize"
    assert item._zone_at(QPointF(150, 198)) == "resize"


def test_shape_excludes_body_so_itemat_misses_inside():
    document = _document_with_region()
    scene = QGraphicsScene()
    item = RegionItem("r_1", document)
    scene.addItem(item)

    assert scene.itemAt(QPointF(150, 100), item.sceneTransform()) is None
    assert scene.itemAt(QPointF(10, 10), item.sceneTransform()) is item


def test_without_undo_stack_a_press_does_not_start_a_drag():
    document = _document_with_region()
    item = RegionItem("r_1", document)

    item.mousePressEvent(_press(QPointF(10, 10)))

    assert item._drag_mode is None


def test_dragging_the_label_bar_moves_the_region_and_pushes_one_undo_step():
    document = _document_with_region()
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    item = RegionItem("r_1", document, undo_stack=undo_stack)
    scene.addItem(item)

    item.mousePressEvent(_press(QPointF(10, 10)))
    item.mouseMoveEvent(_move(QPointF(60, 60)))
    item.mouseReleaseEvent(
        _release(QPointF(60, 60))
    )

    region = document.get_region("r_1")
    assert (region.x, region.y) == (50.0, 50.0)
    assert undo_stack.canUndo()

    undo_stack.undo()
    region = document.get_region("r_1")
    assert (region.x, region.y) == (0.0, 0.0)


def test_dragging_with_no_movement_pushes_nothing():
    document = _document_with_region()
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    item = RegionItem("r_1", document, undo_stack=undo_stack)
    scene.addItem(item)

    item.mousePressEvent(_press(QPointF(10, 10)))
    item.mouseReleaseEvent(
        _release(QPointF(10, 10))
    )

    assert undo_stack.canUndo() is False


def test_dragging_a_region_carries_only_the_cards_inside_it():
    document = _document_with_region(x=0.0, y=0.0, width=300.0, height=200.0)
    document.add_card(Card(id="c_in", x=50.0, y=50.0))  # center (150,110), inside
    document.add_card(Card(id="c_out", x=1000.0, y=1000.0))  # far outside
    document.add_card(Card(id="c_stacked", x=50.0, y=50.0, stack_id="s_1"))
    document.add_stack(Stack(id="s_1", card_ids=["c_stacked"], x=50.0, y=50.0))
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    region_item = RegionItem("r_1", document, undo_stack=undo_stack)
    scene.addItem(region_item)
    card_in_item = CardItem("c_in", document)
    card_in_item.setPos(50.0, 50.0)
    scene.addItem(card_in_item)
    card_out_item = CardItem("c_out", document)
    card_out_item.setPos(1000.0, 1000.0)
    scene.addItem(card_out_item)
    stack_item = StackItem("s_1", document)
    stack_item.setPos(50.0, 50.0)
    scene.addItem(stack_item)

    class _FakeScene:
        """A minimal stand-in exposing just the lookup methods RegionItem
        needs, since a bare QGraphicsScene has neither."""

        def __init__(self, cards, stacks):
            self._cards = cards
            self._stacks = stacks

        def item_for_card(self, card_id):
            return self._cards.get(card_id)

        def item_for_stack(self, stack_id):
            return self._stacks.get(stack_id)

    fake_scene = _FakeScene({"c_in": card_in_item, "c_out": card_out_item}, {"s_1": stack_item})
    region_item.scene = lambda: fake_scene  # type: ignore[method-assign]

    region_item.mousePressEvent(
        _press(QPointF(10, 10))
    )
    region_item.mouseMoveEvent(
        _move(QPointF(30, 30))
    )
    region_item.mouseReleaseEvent(
        _release(QPointF(30, 30))
    )

    assert (document.get_card("c_in").x, document.get_card("c_in").y) == (70.0, 70.0)
    assert (document.get_card("c_out").x, document.get_card("c_out").y) == (1000.0, 1000.0)
    assert (document.get_stack("s_1").x, document.get_stack("s_1").y) == (70.0, 70.0)
    # A stacked card has no CardItem/position of its own -- it rides with
    # its Stack, not independently.
    assert document.get_card("c_stacked").x == 50.0

    undo_stack.undo()
    assert (document.get_card("c_in").x, document.get_card("c_in").y) == (50.0, 50.0)
    assert (document.get_stack("s_1").x, document.get_stack("s_1").y) == (50.0, 50.0)


def test_resize_from_right_edge_grows_width_without_moving_position():
    document = _document_with_region()
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    item = RegionItem("r_1", document, undo_stack=undo_stack)
    scene.addItem(item)

    item.mousePressEvent(
        _press(QPointF(298, 100))
    )
    item.mouseMoveEvent(
        _move(QPointF(378, 100))
    )
    item.mouseReleaseEvent(
        _release(QPointF(378, 100))
    )

    region = document.get_region("r_1")
    assert region.width == 380.0
    assert (region.x, region.y) == (0.0, 0.0)
    assert undo_stack.canUndo()


def test_resize_from_left_edge_moves_x_and_keeps_the_right_edge_fixed():
    document = _document_with_region(x=100.0, y=0.0, width=300.0, height=200.0)
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    item = RegionItem("r_1", document, undo_stack=undo_stack)
    item.setPos(100.0, 0.0)
    scene.addItem(item)

    item.mousePressEvent(
        _mouse_event(QEvent.Type.GraphicsSceneMousePress, QPointF(2, 100), QPointF(102, 100))
    )
    item.mouseMoveEvent(
        _mouse_event(QEvent.Type.GraphicsSceneMouseMove, QPointF(-48, 100), QPointF(52, 100))
    )
    item.mouseReleaseEvent(
        _mouse_event(QEvent.Type.GraphicsSceneMouseRelease, QPointF(-48, 100), QPointF(52, 100))
    )

    region = document.get_region("r_1")
    assert region.width == 350.0
    assert region.x == 50.0
    assert region.x + region.width == 400.0  # right edge unchanged


def test_resize_clamps_to_minimum_size():
    document = _document_with_region()
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    item = RegionItem("r_1", document, undo_stack=undo_stack)
    scene.addItem(item)

    item.mousePressEvent(
        _press(QPointF(298, 198))
    )
    item.mouseMoveEvent(
        _move(QPointF(-500, -500))
    )
    item.mouseReleaseEvent(
        _release(QPointF(-500, -500))
    )

    region = document.get_region("r_1")
    assert (region.width, region.height) == MIN_REGION_SIZE


def test_nested_smaller_region_has_a_higher_z_value_than_a_larger_one():
    document = Document(name="Test")
    document.add_region(Region(id="r_outer", width=600.0, height=400.0))
    document.add_region(Region(id="r_inner", width=200.0, height=150.0))

    outer = RegionItem("r_outer", document)
    inner = RegionItem("r_inner", document)

    assert inner.zValue() > outer.zValue()
    assert outer.zValue() < 1  # regions stay below cards/stacks (z >= 1)


def test_context_menu_offers_label_and_delete():
    document = _document_with_region()
    item = RegionItem("r_1", document, undo_stack=QUndoStack())

    _menu, label_action, delete_action = item._build_context_menu()

    assert label_action.text() == "Label..."
    assert delete_action.text() == "Delete Region"


def test_context_menu_offers_change_label_once_a_label_exists():
    document = _document_with_region(label="Open Questions")
    item = RegionItem("r_1", document, undo_stack=QUndoStack())

    _menu, label_action, _delete_action = item._build_context_menu()

    assert label_action.text() == "Change Label..."


def test_edit_label_via_dialog_pushes_change_label_command(monkeypatch):
    document = _document_with_region()
    undo_stack = QUndoStack()
    item = RegionItem("r_1", document, undo_stack=undo_stack)
    monkeypatch.setattr(
        "indexcards.canvas.region_item.prompt_region_label", lambda *a, **k: "Open Questions"
    )

    item._edit_label_via_dialog()

    assert document.get_region("r_1").label == "Open Questions"
    assert undo_stack.canUndo()


def test_edit_label_via_dialog_cancelled_does_nothing(monkeypatch):
    document = _document_with_region()
    undo_stack = QUndoStack()
    item = RegionItem("r_1", document, undo_stack=undo_stack)
    monkeypatch.setattr("indexcards.canvas.region_item.prompt_region_label", lambda *a, **k: None)

    item._edit_label_via_dialog()

    assert document.get_region("r_1").label == ""
    assert undo_stack.canUndo() is False


def test_delete_via_menu_defers_and_pushes_remove_region_command(qtbot):
    document = _document_with_region()
    undo_stack = QUndoStack()
    item = RegionItem("r_1", document, undo_stack=undo_stack)

    item._delete_via_menu()
    assert "r_1" in document.regions  # deferred, not yet applied

    qtbot.wait(10)

    assert "r_1" not in document.regions
    assert undo_stack.canUndo()
    assert isinstance(undo_stack.command(0), RemoveRegionCommand)


def test_move_causing_a_clean_overlap_yields_the_dragged_region_and_pushes_one_step():
    document = _document_with_region(x=500.0, y=500.0, width=300.0, height=200.0)
    document.add_region(Region(id="other", x=0.0, y=0.0, width=300.0, height=200.0))
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    item = RegionItem("r_1", document, undo_stack=undo_stack)
    item.setPos(500.0, 500.0)
    scene.addItem(item)

    # Dragging r_1 so it would land straddling "other" at (280, 0) -- per
    # the verified stage-2b fixture, this yields r_1 to (300, 0) instead
    # of growing "other".
    item.mousePressEvent(_press(QPointF(10, 10)))
    item.mouseMoveEvent(_move(QPointF(10 + (280.0 - 500.0), 10 + (0.0 - 500.0))))
    item.mouseReleaseEvent(_release(QPointF(10 + (280.0 - 500.0), 10 + (0.0 - 500.0))))

    region = document.get_region("r_1")
    assert (region.x, region.y) == (300.0, 0.0)
    assert document.get_region("other").width == 300.0  # untouched
    assert undo_stack.count() == 1

    undo_stack.undo()
    region = document.get_region("r_1")
    assert (region.x, region.y) == (500.0, 500.0)


def test_move_with_no_valid_resolution_reverts_the_region_and_its_carried_cards(monkeypatch):
    document = _document_with_region()
    document.add_card(Card(id="c_1", x=50.0, y=50.0))  # center (150,110), inside r_1
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    item = RegionItem("r_1", document, undo_stack=undo_stack)
    scene.addItem(item)
    card_item = CardItem("c_1", document)
    card_item.setPos(50.0, 50.0)
    scene.addItem(card_item)

    class _FakeScene:
        def item_for_card(self, card_id):
            return card_item if card_id == "c_1" else None

        def item_for_stack(self, stack_id):
            return None

    item.scene = lambda: _FakeScene()  # type: ignore[method-assign]
    monkeypatch.setattr(region_item_module, "resolve_region_growth", lambda *a, **k: None)

    item.mousePressEvent(_press(QPointF(10, 10)))
    item.mouseMoveEvent(_move(QPointF(60, 60)))
    item.mouseReleaseEvent(_release(QPointF(60, 60)))

    assert undo_stack.canUndo() is False
    assert (document.get_region("r_1").x, document.get_region("r_1").y) == (0.0, 0.0)
    assert (item.pos().x(), item.pos().y()) == (0.0, 0.0)
    assert (document.get_card("c_1").x, document.get_card("c_1").y) == (50.0, 50.0)
    assert (card_item.pos().x(), card_item.pos().y()) == (50.0, 50.0)


def test_resize_triggering_growth_pushes_one_macro_undo_step():
    document = _document_with_region(x=0.0, y=0.0, width=300.0, height=200.0)
    document.add_region(Region(id="other", x=600.0, y=0.0, width=600.0, height=200.0))
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    item = RegionItem("r_1", document, undo_stack=undo_stack)
    scene.addItem(item)

    # Resize r_1's right edge far enough to overlap "other" -- no yield
    # available for a resize, so "other" (or possibly both, if it
    # cascades) must grow instead.
    item.mousePressEvent(_press(QPointF(298, 100)))
    item.mouseMoveEvent(_move(QPointF(680, 100)))
    item.mouseReleaseEvent(_release(QPointF(680, 100)))

    assert undo_stack.count() == 1  # one undo step regardless of how many regions changed
    assert undo_stack.canUndo()
    r1_after, other_after = document.get_region("r_1"), document.get_region("other")

    undo_stack.undo()
    assert document.get_region("r_1").width == 300.0
    assert document.get_region("other").width == 600.0

    undo_stack.redo()
    assert document.get_region("r_1").width == r1_after.width
    assert document.get_region("other").width == other_after.width


def test_resize_with_no_valid_resolution_reverts_geometry(monkeypatch):
    document = _document_with_region(x=0.0, y=0.0, width=300.0, height=200.0)
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    item = RegionItem("r_1", document, undo_stack=undo_stack)
    scene.addItem(item)
    monkeypatch.setattr(region_item_module, "resolve_region_growth", lambda *a, **k: None)

    item.mousePressEvent(_press(QPointF(298, 100)))
    item.mouseMoveEvent(_move(QPointF(378, 100)))
    item.mouseReleaseEvent(_release(QPointF(378, 100)))

    assert undo_stack.canUndo() is False
    assert document.get_region("r_1").width == 300.0
    assert item._width == 300.0
    assert (item.pos().x(), item.pos().y()) == (0.0, 0.0)
