from PySide6.QtCore import QEvent, QPointF
from PySide6.QtGui import QColor, QImage, QPainter, QUndoStack
from PySide6.QtWidgets import (
    QDialog,
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsSceneMouseEvent,
    QMessageBox,
)

from indexcards.canvas.drop_highlight import is_drop_highlighted
from indexcards.canvas.stack_item import StackItem
from indexcards.commands.stack_commands import ExplodeStackCommand
from indexcards.models.card import DEFAULT_CARD_SIZE, Card
from indexcards.models.document import Document
from indexcards.models.stack import Stack
from indexcards.models.theme import Slot, Theme
from indexcards.widgets.stack_dialogs import CreateStackPromptDialog


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


def _document_with_monochrome_stack_theme(background_color: str, slot_hex: str) -> Document:
    theme = Theme(
        id="theme_test",
        name="Test",
        origin="custom",
        background_color=background_color,
        slots=[Slot(id="slot_solid", label="Solid", hex=slot_hex)],
    )
    document = Document(name="Test", theme=theme)
    document.add_card(Card(id="c_1", x=0.0, y=0.0, stack_id="s_1", color_slot="slot_solid"))
    document.add_card(Card(id="c_2", x=0.0, y=0.0, stack_id="s_1", color_slot="slot_solid"))
    document.add_stack(Stack(id="s_1", card_ids=["c_1", "c_2"], x=0.0, y=0.0))
    return document


def test_selected_outline_is_white_on_a_dark_theme():
    # Background and every member card's fill are all dark -- a fixed
    # black outline (the old, pre-contrast-check behavior) would nearly
    # disappear. (0, 0) sits on the top-left corner of the selection
    # stroke, empirically confirmed to render as a pure, unblended pixel.
    document = _document_with_monochrome_stack_theme("#1a1a1a", "#1a1a1a")
    item = StackItem("s_1", document)
    item.setSelected(True)

    image = QImage(300, 300, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        item.paint(painter, None)
    finally:
        painter.end()

    assert image.pixelColor(0, 0).name() == "#ffffff"


def test_selected_outline_is_black_on_a_light_theme():
    document = _document_with_monochrome_stack_theme("#f0f0f0", "#f0f0f0")
    item = StackItem("s_1", document)
    item.setSelected(True)

    image = QImage(300, 300, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        item.paint(painter, None)
    finally:
        painter.end()

    assert image.pixelColor(0, 0).name() == "#000000"


def _document_with_multicolor_stack(slot_hexes: list[str]) -> Document:
    """N cards, each its own distinct-hex slot, added to one stack in the
    given order -- the first hex is therefore card_ids[0], the "top of
    the pile" (the same card the StackOverlay grid puts in its top-left
    cell). Card_ids follow slot_hexes' own order (c_0..c_{n-1})."""
    slots = [
        Slot(id=f"slot_{i}", label="", hex=hex_value) for i, hex_value in enumerate(slot_hexes)
    ]
    theme = Theme(
        id="theme_test", name="Test", origin="custom", background_color="#ffffff", slots=slots
    )
    document = Document(name="Test", theme=theme)
    card_ids = []
    for i in range(len(slot_hexes)):
        card_id = f"c_{i}"
        document.add_card(Card(id=card_id, x=0.0, y=0.0, stack_id="s_1", color_slot=f"slot_{i}"))
        card_ids.append(card_id)
    document.add_stack(Stack(id="s_1", card_ids=card_ids, x=0.0, y=0.0))
    return document


def test_top_face_shows_the_first_added_card_color():
    # Red, then green, then blue -- red is card_ids[0], the top of the
    # pile (the same card the StackOverlay grid shows in its top-left
    # cell), so it's what the top face should show (previously the top
    # face was hardcoded white regardless of any member's color; an
    # earlier version of this fix used card_ids[-1] instead, which
    # showed the *last*-added card and read backwards against the
    # overlay grid's own top-left-to-bottom-right ordering).
    document = _document_with_multicolor_stack(["#ff0000", "#00ff00", "#0000ff"])
    item = StackItem("s_1", document)

    width, height = DEFAULT_CARD_SIZE
    image = QImage(int(width) + 40, int(height) + 40, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        item.paint(painter, None)
    finally:
        painter.end()

    assert image.pixelColor(int(width / 2), int(height / 2)).name() == "#ff0000"


def test_side_bands_read_top_of_pile_to_bottom_of_pile():
    # One band per member card on the extruded edge -- ordered from the
    # edge adjacent to the top face (top of the pile: red, card_ids[0])
    # to the fully-extruded outer edge (bottom of the pile: blue,
    # card_ids[-1]) -- mirroring how a real stack of colored paper's
    # edge would show its composition. Sample points are the analytic
    # midpoint of each band along the front face's depth axis: for a
    # card of DEFAULT_CARD_SIZE and _STACK_DEPTH=20, the front-face
    # point at depth-fraction t is (width/2 + 20*t, height + 20*t).
    document = _document_with_multicolor_stack(["#ff0000", "#00ff00", "#0000ff"])
    item = StackItem("s_1", document)

    width, height = DEFAULT_CARD_SIZE
    image = QImage(int(width) + 40, int(height) + 40, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        item.paint(painter, None)
    finally:
        painter.end()

    depth = 20
    expected_top_to_bottom = ["#ff0000", "#00ff00", "#0000ff"]
    for i, expected_hex in enumerate(expected_top_to_bottom):
        t = (i + 0.5) / 3
        x = int(width / 2 + depth * t)
        y = int(height + depth * t)
        assert image.pixelColor(x, y).name() == expected_hex


def test_empty_stack_falls_back_to_plain_white_top():
    document = Document(name="Test")
    document.add_stack(Stack(id="s_1", card_ids=[], x=0.0, y=0.0))
    item = StackItem("s_1", document)

    width, height = DEFAULT_CARD_SIZE
    image = QImage(int(width) + 40, int(height) + 40, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        item.paint(painter, None)
    finally:
        painter.end()

    assert image.pixelColor(int(width / 2), int(height / 2)).name() == "#ffffff"


def test_label_text_contrasts_against_a_dark_top_color():
    # Previously the label was hardcoded black, which would be all but
    # invisible on a stack whose top card is black -- it must now track
    # the top face's own resolved color the same way CardItem's own text
    # does (auto_text_color/slot.text_color).
    document = _document_with_multicolor_stack(["#000000"])
    document.set_stack_label("s_1", "Chapter 1")
    item = StackItem("s_1", document)

    width, height = DEFAULT_CARD_SIZE
    image = QImage(int(width) + 40, int(height) + 40, QImage.Format.Format_ARGB32)
    image.fill(QColor("black"))
    painter = QPainter(image)
    try:
        item.paint(painter, None)
    finally:
        painter.end()

    label_row_y = int(height / 2)
    assert any(
        image.pixelColor(x, label_row_y).name() == "#ffffff"
        for x in range(10, int(width) - 10)
    )


def test_without_undo_stack_item_is_not_movable():
    document = _document_with_stack()
    item = StackItem("s_1", document)
    assert not (item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable)


def test_with_undo_stack_item_is_movable():
    document = _document_with_stack()
    item = StackItem("s_1", document, undo_stack=QUndoStack())
    assert item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable


def _drag(
    item: StackItem, to_x: float, to_y: float, scene_pos: QPointF | None = None
) -> None:
    press = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMousePress)
    item.mousePressEvent(press)

    item.setPos(to_x, to_y)

    release = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMouseRelease)
    if scene_pos is not None:
        release.setScenePos(scene_pos)
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


def _document_with_two_stacks() -> Document:
    document = Document(name="Test")
    document.add_card(Card(id="c_1", stack_id="s_dropped"))
    document.add_card(Card(id="c_2", stack_id="s_dropped"))
    document.add_card(Card(id="c_3", stack_id="s_target"))
    document.add_stack(Stack(id="s_dropped", card_ids=["c_1", "c_2"], x=0.0, y=0.0))
    document.add_stack(Stack(id="s_target", card_ids=["c_3"], x=500.0, y=500.0, label="Target"))
    return document


def test_drag_onto_another_stack_confirmed_merges(monkeypatch):
    monkeypatch.setattr(
        CreateStackPromptDialog,
        "exec",
        lambda self: (self.label_edit.setText("Merged"), QDialog.DialogCode.Accepted)[1],
    )
    document = _document_with_two_stacks()
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    dropped_item = StackItem("s_dropped", document, undo_stack=undo_stack)
    target_item = StackItem("s_target", document, undo_stack=undo_stack)
    target_item.setPos(500.0, 500.0)
    scene.addItem(dropped_item)
    scene.addItem(target_item)

    width, height = DEFAULT_CARD_SIZE
    drop_point = QPointF(500.0 + width / 2, 500.0 + height / 2)
    _drag(dropped_item, 500.0, 500.0, scene_pos=drop_point)

    assert "s_dropped" not in document.stacks
    assert "s_target" not in document.stacks
    (merged_id,) = [sid for sid in document.stacks if sid not in ("s_dropped", "s_target")]
    merged_stack = document.get_stack(merged_id)
    assert merged_stack.card_ids == ["c_1", "c_2", "c_3"]
    assert merged_stack.label == "Merged"
    assert (merged_stack.x, merged_stack.y) == (500.0, 500.0)
    assert undo_stack.canUndo()

    undo_stack.undo()
    assert set(document.stacks) == {"s_dropped", "s_target"}
    assert document.get_stack("s_dropped").card_ids == ["c_1", "c_2"]
    assert document.get_stack("s_target").card_ids == ["c_3"]


def test_drag_onto_another_stack_cancelled_falls_back_to_move(monkeypatch):
    monkeypatch.setattr(CreateStackPromptDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    document = _document_with_two_stacks()
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    dropped_item = StackItem("s_dropped", document, undo_stack=undo_stack)
    target_item = StackItem("s_target", document, undo_stack=undo_stack)
    target_item.setPos(500.0, 500.0)
    scene.addItem(dropped_item)
    scene.addItem(target_item)

    width, height = DEFAULT_CARD_SIZE
    drop_point = QPointF(500.0 + width / 2, 500.0 + height / 2)
    _drag(dropped_item, 500.0, 500.0, scene_pos=drop_point)

    assert set(document.stacks) == {"s_dropped", "s_target"}
    assert (document.get_stack("s_dropped").x, document.get_stack("s_dropped").y) == (500.0, 500.0)
    assert undo_stack.canUndo()  # the plain move is still a real, undoable step


def test_drag_missing_other_stack_still_just_moves():
    document = _document_with_two_stacks()
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    dropped_item = StackItem("s_dropped", document, undo_stack=undo_stack)
    target_item = StackItem("s_target", document, undo_stack=undo_stack)
    target_item.setPos(500.0, 500.0)
    scene.addItem(dropped_item)
    scene.addItem(target_item)

    drop_point = QPointF(1500.0, 1500.0)  # far from either stack
    _drag(dropped_item, 300.0, 300.0, scene_pos=drop_point)

    assert set(document.stacks) == {"s_dropped", "s_target"}
    assert (document.get_stack("s_dropped").x, document.get_stack("s_dropped").y) == (300.0, 300.0)


def _move_event(scene_pos: QPointF) -> QGraphicsSceneMouseEvent:
    event = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMouseMove)
    event.setScenePos(scene_pos)
    return event


def test_drag_move_onto_another_stack_highlights_it():
    document = _document_with_two_stacks()
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    dropped_item = StackItem("s_dropped", document, undo_stack=undo_stack)
    target_item = StackItem("s_target", document, undo_stack=undo_stack)
    target_item.setPos(500.0, 500.0)
    scene.addItem(dropped_item)
    scene.addItem(target_item)

    dropped_item.mousePressEvent(QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMousePress))
    dropped_item.setPos(500.0, 500.0)
    width, height = DEFAULT_CARD_SIZE
    over_target = QPointF(500.0 + width / 2, 500.0 + height / 2)

    dropped_item.mouseMoveEvent(_move_event(over_target))

    assert is_drop_highlighted(target_item)


def test_drag_move_off_another_stack_clears_the_highlight():
    document = _document_with_two_stacks()
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    dropped_item = StackItem("s_dropped", document, undo_stack=undo_stack)
    target_item = StackItem("s_target", document, undo_stack=undo_stack)
    target_item.setPos(500.0, 500.0)
    scene.addItem(dropped_item)
    scene.addItem(target_item)

    dropped_item.mousePressEvent(QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMousePress))
    width, height = DEFAULT_CARD_SIZE
    dropped_item.setPos(500.0, 500.0)
    dropped_item.mouseMoveEvent(_move_event(QPointF(500.0 + width / 2, 500.0 + height / 2)))
    assert is_drop_highlighted(target_item)

    dropped_item.setPos(1500.0, 1500.0)
    dropped_item.mouseMoveEvent(_move_event(QPointF(1500.0, 1500.0)))

    assert not is_drop_highlighted(target_item)


def test_drop_highlight_cleared_after_confirmed_stack_merge(monkeypatch):
    monkeypatch.setattr(
        CreateStackPromptDialog,
        "exec",
        lambda self: (self.label_edit.setText("x"), QDialog.DialogCode.Accepted)[1],
    )
    document = _document_with_two_stacks()
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    dropped_item = StackItem("s_dropped", document, undo_stack=undo_stack)
    target_item = StackItem("s_target", document, undo_stack=undo_stack)
    target_item.setPos(500.0, 500.0)
    scene.addItem(dropped_item)
    scene.addItem(target_item)

    dropped_item.mousePressEvent(QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMousePress))
    width, height = DEFAULT_CARD_SIZE
    dropped_item.setPos(500.0, 500.0)
    over_target = QPointF(500.0 + width / 2, 500.0 + height / 2)
    dropped_item.mouseMoveEvent(_move_event(over_target))
    assert is_drop_highlighted(target_item)

    release = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMouseRelease)
    release.setScenePos(over_target)
    dropped_item.mouseReleaseEvent(release)

    assert not is_drop_highlighted(target_item)


def test_drop_highlight_cleared_after_cancelled_stack_merge(monkeypatch):
    monkeypatch.setattr(CreateStackPromptDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    document = _document_with_two_stacks()
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    dropped_item = StackItem("s_dropped", document, undo_stack=undo_stack)
    target_item = StackItem("s_target", document, undo_stack=undo_stack)
    target_item.setPos(500.0, 500.0)
    scene.addItem(dropped_item)
    scene.addItem(target_item)

    dropped_item.mousePressEvent(QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMousePress))
    width, height = DEFAULT_CARD_SIZE
    dropped_item.setPos(500.0, 500.0)
    over_target = QPointF(500.0 + width / 2, 500.0 + height / 2)
    dropped_item.mouseMoveEvent(_move_event(over_target))
    assert is_drop_highlighted(target_item)

    release = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMouseRelease)
    release.setScenePos(over_target)
    dropped_item.mouseReleaseEvent(release)

    assert not is_drop_highlighted(target_item)


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


def test_search_match_count_none_by_default():
    document = _document_with_stack()
    item = StackItem("s_1", document)
    assert item._search_match_count is None
    assert item.opacity() == 1.0


def test_set_search_match_count_zero_dims_the_item():
    document = _document_with_stack()
    item = StackItem("s_1", document)

    item.set_search_match_count(0)

    assert item.opacity() < 1.0


def test_set_search_match_count_positive_is_full_opacity():
    document = _document_with_stack()
    item = StackItem("s_1", document)
    item.set_search_match_count(0)

    item.set_search_match_count(1)

    assert item.opacity() == 1.0


def test_set_search_match_count_none_restores_full_opacity():
    document = _document_with_stack()
    item = StackItem("s_1", document)
    item.set_search_match_count(0)

    item.set_search_match_count(None)

    assert item.opacity() == 1.0


def test_set_search_match_count_same_value_is_a_noop():
    document = _document_with_stack()
    item = StackItem("s_1", document)
    item.set_search_match_count(1)
    item.setOpacity(0.7)  # a value set_search_match_count would never itself produce

    item.set_search_match_count(1)  # same value again

    assert item.opacity() == 0.7  # untouched -- confirms the early-return guard


def test_paint_with_a_positive_match_count_does_not_crash():
    document = _document_with_stack()
    item = StackItem("s_1", document)
    item.set_search_match_count(1)

    image = QImage(300, 300, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        item.paint(painter, None)
    finally:
        painter.end()


def test_paint_with_zero_match_count_does_not_crash():
    document = _document_with_stack()
    item = StackItem("s_1", document)
    item.set_search_match_count(0)

    image = QImage(300, 300, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        item.paint(painter, None)
    finally:
        painter.end()
