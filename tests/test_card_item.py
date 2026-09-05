from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFocusEvent,
    QFont,
    QImage,
    QKeyEvent,
    QPainter,
    QTextCursor,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QDialog,
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsSceneMouseEvent,
    QInputDialog,
    QMessageBox,
)

from indexcards.canvas.card_item import (
    _CORNER_RADIUS,
    _TEXT_MARGIN,
    CardItem,
    _CardTextItem,
    _center_quartile_contains,
    _desaturated,
    _dimmed_text_color,
)
from indexcards.canvas.drop_highlight import is_drop_highlighted
from indexcards.canvas.stack_item import StackItem
from indexcards.models.card import DEFAULT_CARD_SIZE, MAX_TEXT_LENGTH, Card
from indexcards.models.document import Document
from indexcards.models.link import Link
from indexcards.models.stack import Stack
from indexcards.models.theme import Slot
from indexcards.widgets.stack_dialogs import CreateStackPromptDialog


def test_desaturated_removes_saturation_but_keeps_lightness():
    original = QColor("#F6E27A")  # a saturated yellow
    result = _desaturated(original)

    assert result.saturation() == 0
    assert result.value() == original.value()


def test_dimmed_text_color_lightens_black_to_fixed_gray():
    # auto_text_color() only ever returns pure black/white, which already
    # have zero saturation — _desaturated() alone would be a no-op, so
    # dimmed text needs an explicit target gray instead. Both polarities
    # converge on the same value rather than each blending partway toward
    # the other, so black text doesn't end up dimmed to a still-too-dark
    # shade of gray. Compared via .name() rather than QColor equality —
    # a color built via fromHsv() (saturation 0, hue -1) doesn't compare
    # equal to the same visual color built via fromRgb()/the hex string.
    assert _dimmed_text_color(QColor("#000000")).name() == "#999999"


def test_dimmed_text_color_darkens_white_to_fixed_gray():
    assert _dimmed_text_color(QColor("#FFFFFF")).name() == "#999999"


def test_dimmed_text_color_desaturates_a_colored_override_to_the_same_gray():
    assert _dimmed_text_color(QColor("#F6E27A")).name() == "#999999"


def test_corners_are_sharp():
    assert _CORNER_RADIUS == 0


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


def test_text_item_renders_markdown_as_plain_text():
    document = _document_with_card()
    item = CardItem("c_1", document)

    assert item._text_item.toPlainText() == "Bold idea"


def test_refresh_picks_up_document_text_change():
    document = _document_with_card()
    item = CardItem("c_1", document)

    document.set_card_text("c_1", "Updated *text*")
    item.refresh()

    assert item._text_item.toPlainText() == "Updated text"


def test_refresh_does_not_clobber_in_progress_edit():
    document = _document_with_card()
    stack = QUndoStack()
    scene = QGraphicsScene()
    item = CardItem("c_1", document, undo_stack=stack)
    scene.addItem(item)

    item.enter_edit_mode()
    item._text_item.setPlainText("still typing")
    document.set_card_text("c_1", "changed elsewhere")
    item.refresh()

    assert item._text_item.toPlainText() == "still typing"


def test_clips_children_to_shape_flag_is_set():
    document = _document_with_card()
    item = CardItem("c_1", document)
    assert item.flags() & QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape


def test_renders_as_single_line_true_for_short_text():
    document = _document_with_card()  # "**Bold** idea" — short, single line
    item = CardItem("c_1", document)
    assert item._renders_as_single_line()


def test_renders_as_single_line_false_for_wrapped_text():
    document = Document(name="Test")
    document.add_card(
        Card(id="c_1", text="This is a fairly long single sentence that will wrap to two lines")
    )
    item = CardItem("c_1", document)
    assert not item._renders_as_single_line()


def test_renders_as_single_line_false_for_explicit_multiline_text():
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="line one\n\nline two"))
    item = CardItem("c_1", document)
    assert not item._renders_as_single_line()


def test_short_text_renders_centered_horizontally_and_vertically():
    document = _document_with_card()  # "**Bold** idea" — short, single line
    item = CardItem("c_1", document)

    option = item._text_item.document().defaultTextOption()
    assert option.alignment() == Qt.AlignmentFlag.AlignHCenter
    _width, height = DEFAULT_CARD_SIZE
    content_height = item._text_item.document().size().height()
    expected_y = max(_TEXT_MARGIN, (height - content_height) / 2)
    assert item._text_item.pos().x() == _TEXT_MARGIN
    assert abs(item._text_item.pos().y() - expected_y) < 0.5
    assert expected_y > _TEXT_MARGIN  # sanity: actually centered, not just at the margin


def test_wrapped_text_renders_left_and_top():
    document = Document(name="Test")
    document.add_card(
        Card(id="c_1", text="This is a fairly long single sentence that will wrap to two lines")
    )
    item = CardItem("c_1", document)

    option = item._text_item.document().defaultTextOption()
    assert option.alignment() == Qt.AlignmentFlag.AlignLeft
    assert item._text_item.pos() == QPointF(_TEXT_MARGIN, _TEXT_MARGIN)


def test_multiline_text_renders_left_and_top():
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="line one\n\nline two"))
    item = CardItem("c_1", document)

    option = item._text_item.document().defaultTextOption()
    assert option.alignment() == Qt.AlignmentFlag.AlignLeft
    assert item._text_item.pos() == QPointF(_TEXT_MARGIN, _TEXT_MARGIN)


def test_entering_edit_mode_resets_centered_card_to_left_top():
    document = _document_with_card()  # would render centered
    stack = QUndoStack()
    scene = QGraphicsScene()
    item = CardItem("c_1", document, undo_stack=stack)
    scene.addItem(item)
    option_before = item._text_item.document().defaultTextOption()
    assert option_before.alignment() == Qt.AlignmentFlag.AlignHCenter

    item.enter_edit_mode()

    option_after = item._text_item.document().defaultTextOption()
    assert option_after.alignment() == Qt.AlignmentFlag.AlignLeft
    assert item._text_item.pos() == QPointF(_TEXT_MARGIN, _TEXT_MARGIN)


def test_exiting_edit_mode_without_change_restores_centered_layout():
    document = _document_with_card()  # would render centered
    stack = QUndoStack()
    scene = QGraphicsScene()
    item = CardItem("c_1", document, undo_stack=stack)
    scene.addItem(item)
    item.enter_edit_mode()

    item._on_text_focus_out()  # no text change made

    option = item._text_item.document().defaultTextOption()
    assert option.alignment() == Qt.AlignmentFlag.AlignHCenter
    assert item._text_item.pos().y() > _TEXT_MARGIN
    assert stack.canUndo() is False  # confirms this was genuinely a no-op edit


def test_without_undo_stack_item_is_not_movable():
    document = _document_with_card()
    item = CardItem("c_1", document)
    assert not (item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable)


def test_with_undo_stack_item_is_movable():
    document = _document_with_card()
    item = CardItem("c_1", document, undo_stack=QUndoStack())
    assert item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable


def test_movable_false_suppresses_item_is_movable_even_with_undo_stack():
    document = _document_with_card()
    item = CardItem("c_1", document, undo_stack=QUndoStack(), movable=False)
    assert not (item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable)


def test_movable_false_stays_suppressed_after_edit_session_ends():
    document = _document_with_card()
    stack = QUndoStack()
    scene = QGraphicsScene()
    item = CardItem("c_1", document, undo_stack=stack, movable=False)
    scene.addItem(item)

    item.enter_edit_mode()
    item._on_text_focus_out()

    assert not (item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable)


def _drag(
    item: CardItem, to_x: float, to_y: float, scene_pos: QPointF | None = None
) -> None:
    press = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMousePress)
    item.mousePressEvent(press)

    item.setPos(to_x, to_y)

    release = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMouseRelease)
    if scene_pos is not None:
        release.setScenePos(scene_pos)
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


def test_center_quartile_contains_center_point():
    from PySide6.QtCore import QRectF

    rect = QRectF(0, 0, 200, 120)
    assert _center_quartile_contains(rect, QPointF(100, 60))


def test_center_quartile_excludes_corner_point():
    from PySide6.QtCore import QRectF

    rect = QRectF(0, 0, 200, 120)
    assert not _center_quartile_contains(rect, QPointF(5, 5))


def test_center_quartile_boundary_is_inclusive():
    from PySide6.QtCore import QRectF

    rect = QRectF(0, 0, 200, 120)
    # Exactly 25% inset from each edge — the boundary of the central half.
    assert _center_quartile_contains(rect, QPointF(50, 30))
    assert _center_quartile_contains(rect, QPointF(150, 90))


def _two_card_document() -> Document:
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    document.add_card(Card(id="c_2", x=500.0, y=500.0))
    return document


def _card_item(document: Document, card_id: str, undo_stack: QUndoStack) -> CardItem:
    """CardItem doesn't self-position from the Document — that's normally
    CanvasScene's job (item.setPos(card.x, card.y) right after
    construction) — so tests building items directly must do it too."""
    card = document.get_card(card_id)
    item = CardItem(card_id, document, undo_stack=undo_stack)
    item.setPos(card.x, card.y)
    return item


def _stack_item(document: Document, stack_id: str, undo_stack: QUndoStack) -> StackItem:
    stack = document.get_stack(stack_id)
    item = StackItem(stack_id, document, undo_stack=undo_stack)
    item.setPos(stack.x, stack.y)
    return item


def test_resolve_drop_target_finds_card_under_point():
    document = _two_card_document()
    stack = QUndoStack()
    scene = QGraphicsScene()
    item_1 = _card_item(document, "c_1", stack)
    item_2 = _card_item(document, "c_2", stack)
    scene.addItem(item_1)
    scene.addItem(item_2)

    width, height = DEFAULT_CARD_SIZE
    center_of_c2 = QPointF(500.0 + width / 2, 500.0 + height / 2)
    target = item_1._resolve_drop_target(center_of_c2, {"c_1"})

    assert target is item_2


def test_resolve_drop_target_excludes_given_card_ids():
    document = _two_card_document()
    stack = QUndoStack()
    scene = QGraphicsScene()
    item_1 = _card_item(document, "c_1", stack)
    item_2 = _card_item(document, "c_2", stack)
    scene.addItem(item_1)
    scene.addItem(item_2)

    width, height = DEFAULT_CARD_SIZE
    center_of_c2 = QPointF(500.0 + width / 2, 500.0 + height / 2)
    target = item_1._resolve_drop_target(center_of_c2, {"c_1", "c_2"})

    assert target is None


def test_resolve_drop_target_returns_none_over_empty_space():
    document = _two_card_document()
    stack = QUndoStack()
    scene = QGraphicsScene()
    item_1 = _card_item(document, "c_1", stack)
    scene.addItem(item_1)

    target = item_1._resolve_drop_target(QPointF(9000.0, 9000.0), {"c_1"})

    assert target is None


def test_resolve_drop_target_finds_stack_item():
    document = _two_card_document()
    document.add_stack(Stack(id="s_1", x=500.0, y=500.0))
    stack = QUndoStack()
    scene = QGraphicsScene()
    item_1 = _card_item(document, "c_1", stack)
    stack_item = _stack_item(document, "s_1", stack)
    scene.addItem(item_1)
    scene.addItem(stack_item)

    target = item_1._resolve_drop_target(QPointF(510.0, 510.0), {"c_1"})

    assert target is stack_item


def test_drag_onto_card_center_quartile_confirmed_creates_stack(monkeypatch, qtbot):
    monkeypatch.setattr(
        CreateStackPromptDialog,
        "exec",
        lambda self: (self.label_edit.setText("Chapter 1"), QDialog.DialogCode.Accepted)[1],
    )
    document = _two_card_document()
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    item_1 = _card_item(document, "c_1", undo_stack)
    item_2 = _card_item(document, "c_2", undo_stack)
    scene.addItem(item_1)
    scene.addItem(item_2)

    width, height = DEFAULT_CARD_SIZE
    drop_point = QPointF(500.0 + width / 2, 500.0 + height / 2)
    _drag(item_1, 500.0, 500.0, scene_pos=drop_point)

    new_stack_id = document.get_card("c_2").stack_id
    assert new_stack_id is not None
    assert document.get_card("c_1").stack_id == new_stack_id
    assert set(document.get_stack(new_stack_id).card_ids) == {"c_1", "c_2"}
    assert document.get_stack(new_stack_id).label == "Chapter 1"
    # New stack replaces the target card's position/slot.
    assert (document.get_stack(new_stack_id).x, document.get_stack(new_stack_id).y) == (
        500.0,
        500.0,
    )


def test_drag_onto_card_center_quartile_cancelled_falls_back_to_move(monkeypatch):
    monkeypatch.setattr(
        CreateStackPromptDialog, "exec", lambda self: QDialog.DialogCode.Rejected
    )
    document = _two_card_document()
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    item_1 = _card_item(document, "c_1", undo_stack)
    item_2 = _card_item(document, "c_2", undo_stack)
    scene.addItem(item_1)
    scene.addItem(item_2)

    width, height = DEFAULT_CARD_SIZE
    drop_point = QPointF(500.0 + width / 2, 500.0 + height / 2)
    _drag(item_1, 500.0, 500.0, scene_pos=drop_point)

    assert document.get_card("c_1").stack_id is None
    assert document.get_card("c_2").stack_id is None
    assert (document.get_card("c_1").x, document.get_card("c_1").y) == (500.0, 500.0)


def test_drag_onto_card_outside_center_quartile_does_not_create_stack():
    document = _two_card_document()
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    item_1 = _card_item(document, "c_1", undo_stack)
    item_2 = _card_item(document, "c_2", undo_stack)
    scene.addItem(item_1)
    scene.addItem(item_2)

    # Drop point lands on c_2's card, but right at its corner (well outside
    # the central 50%x50% quartile).
    drop_point = QPointF(500.0 + 2.0, 500.0 + 2.0)
    _drag(item_1, 500.0, 500.0, scene_pos=drop_point)

    assert document.get_card("c_1").stack_id is None
    assert document.get_card("c_2").stack_id is None
    assert document.get_card("c_1").x == 500.0


def test_drag_onto_stack_item_adds_card_no_dialog_needed():
    document = _two_card_document()
    document.add_stack(Stack(id="s_1", x=500.0, y=500.0))
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    item_1 = _card_item(document, "c_1", undo_stack)
    stack_item = _stack_item(document, "s_1", undo_stack)
    scene.addItem(item_1)
    scene.addItem(stack_item)

    _drag(item_1, 500.0, 500.0, scene_pos=QPointF(510.0, 510.0))

    assert document.get_card("c_1").stack_id == "s_1"
    assert document.get_stack("s_1").card_ids == ["c_1"]


def _move_event(scene_pos: QPointF) -> QGraphicsSceneMouseEvent:
    event = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMouseMove)
    event.setScenePos(scene_pos)
    return event


def test_drag_move_into_center_quartile_highlights_target_card():
    document = _two_card_document()
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    item_1 = _card_item(document, "c_1", undo_stack)
    item_2 = _card_item(document, "c_2", undo_stack)
    scene.addItem(item_1)
    scene.addItem(item_2)

    item_1.mousePressEvent(QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMousePress))
    item_1.setPos(500.0, 500.0)
    width, height = DEFAULT_CARD_SIZE
    center_of_c2 = QPointF(500.0 + width / 2, 500.0 + height / 2)

    item_1.mouseMoveEvent(_move_event(center_of_c2))

    assert is_drop_highlighted(item_2)


def test_drag_move_outside_center_quartile_does_not_highlight_target_card():
    document = _two_card_document()
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    item_1 = _card_item(document, "c_1", undo_stack)
    item_2 = _card_item(document, "c_2", undo_stack)
    scene.addItem(item_1)
    scene.addItem(item_2)

    item_1.mousePressEvent(QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMousePress))
    item_1.setPos(500.0, 500.0)
    # Lands on c_2's card, but at its corner (well outside the center
    # 50%x50% quartile) -- same point used by the release-time regression
    # test above.
    corner_of_c2 = QPointF(500.0 + 2.0, 500.0 + 2.0)

    item_1.mouseMoveEvent(_move_event(corner_of_c2))

    assert not is_drop_highlighted(item_2)


def test_drag_move_onto_stack_highlights_it_anywhere_within_bounds():
    document = _two_card_document()
    document.add_stack(Stack(id="s_1", x=500.0, y=500.0))
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    item_1 = _card_item(document, "c_1", undo_stack)
    stack_item = _stack_item(document, "s_1", undo_stack)
    scene.addItem(item_1)
    scene.addItem(stack_item)

    item_1.mousePressEvent(QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMousePress))
    item_1.setPos(500.0, 500.0)
    # No quartile requirement for a stack target -- near the corner is fine.
    corner_of_stack = QPointF(500.0 + 2.0, 500.0 + 2.0)

    item_1.mouseMoveEvent(_move_event(corner_of_stack))

    assert is_drop_highlighted(stack_item)


def test_drag_move_transfers_highlight_between_targets():
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    document.add_card(Card(id="c_2", x=500.0, y=500.0))
    document.add_card(Card(id="c_3", x=1000.0, y=500.0))
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    item_1 = _card_item(document, "c_1", undo_stack)
    item_2 = _card_item(document, "c_2", undo_stack)
    item_3 = _card_item(document, "c_3", undo_stack)
    scene.addItem(item_1)
    scene.addItem(item_2)
    scene.addItem(item_3)

    item_1.mousePressEvent(QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMousePress))
    width, height = DEFAULT_CARD_SIZE
    item_1.setPos(500.0, 500.0)
    item_1.mouseMoveEvent(_move_event(QPointF(500.0 + width / 2, 500.0 + height / 2)))
    assert is_drop_highlighted(item_2)

    item_1.setPos(1000.0, 500.0)
    item_1.mouseMoveEvent(_move_event(QPointF(1000.0 + width / 2, 500.0 + height / 2)))

    assert not is_drop_highlighted(item_2)
    assert is_drop_highlighted(item_3)


def test_multi_card_drag_move_never_highlights_anything():
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    document.add_card(Card(id="c_2", x=100.0, y=0.0))
    document.add_card(Card(id="c_3", x=500.0, y=500.0))
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    item_1 = _card_item(document, "c_1", undo_stack)
    item_2 = _card_item(document, "c_2", undo_stack)
    item_3 = _card_item(document, "c_3", undo_stack)
    scene.addItem(item_1)
    scene.addItem(item_2)
    scene.addItem(item_3)
    item_1.setSelected(True)
    item_2.setSelected(True)

    item_1.mousePressEvent(QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMousePress))
    width, height = DEFAULT_CARD_SIZE
    item_1.setPos(500.0, 500.0)
    item_1.mouseMoveEvent(_move_event(QPointF(500.0 + width / 2, 500.0 + height / 2)))

    assert not is_drop_highlighted(item_3)


def test_drop_highlight_cleared_after_confirmed_merge_onto_card(monkeypatch):
    monkeypatch.setattr(
        CreateStackPromptDialog,
        "exec",
        lambda self: (self.label_edit.setText("x"), QDialog.DialogCode.Accepted)[1],
    )
    document = _two_card_document()
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    item_1 = _card_item(document, "c_1", undo_stack)
    item_2 = _card_item(document, "c_2", undo_stack)
    scene.addItem(item_1)
    scene.addItem(item_2)

    item_1.mousePressEvent(QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMousePress))
    item_1.setPos(500.0, 500.0)
    width, height = DEFAULT_CARD_SIZE
    center_of_c2 = QPointF(500.0 + width / 2, 500.0 + height / 2)
    item_1.mouseMoveEvent(_move_event(center_of_c2))
    assert is_drop_highlighted(item_2)

    release = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMouseRelease)
    release.setScenePos(center_of_c2)
    item_1.mouseReleaseEvent(release)

    assert not is_drop_highlighted(item_2)


def test_drop_highlight_cleared_after_cancelled_merge_onto_card(monkeypatch):
    monkeypatch.setattr(CreateStackPromptDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    document = _two_card_document()
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    item_1 = _card_item(document, "c_1", undo_stack)
    item_2 = _card_item(document, "c_2", undo_stack)
    scene.addItem(item_1)
    scene.addItem(item_2)

    item_1.mousePressEvent(QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMousePress))
    item_1.setPos(500.0, 500.0)
    width, height = DEFAULT_CARD_SIZE
    center_of_c2 = QPointF(500.0 + width / 2, 500.0 + height / 2)
    item_1.mouseMoveEvent(_move_event(center_of_c2))
    assert is_drop_highlighted(item_2)

    release = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMouseRelease)
    release.setScenePos(center_of_c2)
    item_1.mouseReleaseEvent(release)

    assert not is_drop_highlighted(item_2)


def test_multi_card_drag_onto_stack_confirmed_adds_all(monkeypatch):
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.Yes)
    document = _two_card_document()
    document.add_stack(Stack(id="s_1", x=900.0, y=900.0))
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    item_1 = _card_item(document, "c_1", undo_stack)
    item_2 = _card_item(document, "c_2", undo_stack)
    stack_item = _stack_item(document, "s_1", undo_stack)
    scene.addItem(item_1)
    scene.addItem(item_2)
    scene.addItem(stack_item)
    item_1.setSelected(True)
    item_2.setSelected(True)

    _drag(item_1, 890.0, 890.0, scene_pos=QPointF(910.0, 910.0))

    assert document.get_card("c_1").stack_id == "s_1"
    assert document.get_card("c_2").stack_id == "s_1"
    assert set(document.get_stack("s_1").card_ids) == {"c_1", "c_2"}


def test_multi_card_drag_onto_stack_cancelled_falls_back_to_move(monkeypatch):
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.Cancel)
    document = _two_card_document()
    document.add_stack(Stack(id="s_1", x=900.0, y=900.0))
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    item_1 = _card_item(document, "c_1", undo_stack)
    item_2 = _card_item(document, "c_2", undo_stack)
    stack_item = _stack_item(document, "s_1", undo_stack)
    scene.addItem(item_1)
    scene.addItem(item_2)
    scene.addItem(stack_item)
    item_1.setSelected(True)
    item_2.setSelected(True)

    _drag(item_1, 890.0, 890.0, scene_pos=QPointF(910.0, 910.0))

    assert document.get_card("c_1").stack_id is None
    assert document.get_card("c_2").stack_id is None
    assert document.get_card("c_1").x == 890.0


def test_multi_card_drag_onto_plain_card_does_nothing_special_but_commits_both_moves():
    document = _two_card_document()
    document.add_card(Card(id="c_3", x=1000.0, y=1000.0))
    undo_stack = QUndoStack()
    scene = QGraphicsScene()
    item_1 = _card_item(document, "c_1", undo_stack)
    item_2 = _card_item(document, "c_2", undo_stack)
    item_3 = _card_item(document, "c_3", undo_stack)
    scene.addItem(item_1)
    scene.addItem(item_2)
    scene.addItem(item_3)
    item_1.setSelected(True)
    item_2.setSelected(True)

    # Simulate item_2 having moved alongside item_1 during the same drag
    # (Qt moves every selected+movable item together; only the pressed
    # item — item_1 — receives press/release events).
    press = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMousePress)
    item_1.mousePressEvent(press)
    item_1.setPos(400.0, 400.0)
    item_2.setPos(900.0, 900.0)
    release = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMouseRelease)
    release.setScenePos(QPointF(1000.0, 1000.0))  # lands on c_3, a plain card
    item_1.mouseReleaseEvent(release)

    # Regression: previously only the pressed item's (item_1's) new
    # position was ever committed to the Document — item_2's move was
    # visual-only. Both must now be persisted as one undo step.
    assert (document.get_card("c_1").x, document.get_card("c_1").y) == (400.0, 400.0)
    assert (document.get_card("c_2").x, document.get_card("c_2").y) == (900.0, 900.0)
    assert document.get_card("c_1").stack_id is None
    assert document.get_card("c_2").stack_id is None
    assert undo_stack.canUndo()

    undo_stack.undo()
    assert (document.get_card("c_1").x, document.get_card("c_1").y) == (0.0, 0.0)
    assert (document.get_card("c_2").x, document.get_card("c_2").y) == (500.0, 500.0)


def _press_event(button=Qt.MouseButton.LeftButton) -> QGraphicsSceneMouseEvent:
    event = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMousePress)
    event.setButton(button)
    return event


def _release_event(button=Qt.MouseButton.LeftButton) -> QGraphicsSceneMouseEvent:
    event = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMouseRelease)
    event.setButton(button)
    return event


def test_selecting_movable_card_shows_grab_hand_cursor():
    document = _document_with_card()
    scene = QGraphicsScene()
    item = CardItem("c_1", document, undo_stack=QUndoStack())
    scene.addItem(item)

    item.setSelected(True)

    assert item.hasCursor()
    assert item.cursor().shape() == Qt.CursorShape.OpenHandCursor


def test_deselecting_card_clears_cursor():
    document = _document_with_card()
    scene = QGraphicsScene()
    item = CardItem("c_1", document, undo_stack=QUndoStack())
    scene.addItem(item)
    item.setSelected(True)

    item.setSelected(False)

    assert not item.hasCursor()


def test_selecting_non_movable_card_does_not_show_cursor():
    document = _document_with_card()
    scene = QGraphicsScene()
    item = CardItem("c_1", document)
    scene.addItem(item)

    item.setSelected(True)

    assert not item.hasCursor()


def test_pressing_movable_card_shows_closed_hand_cursor():
    document = _document_with_card()
    scene = QGraphicsScene()
    item = CardItem("c_1", document, undo_stack=QUndoStack())
    scene.addItem(item)

    item.mousePressEvent(_press_event())

    assert item.cursor().shape() == Qt.CursorShape.ClosedHandCursor


def test_releasing_after_press_restores_grab_hand_when_still_selected():
    document = _document_with_card()
    scene = QGraphicsScene()
    item = CardItem("c_1", document, undo_stack=QUndoStack())
    scene.addItem(item)

    item.mousePressEvent(_press_event())
    item.mouseReleaseEvent(_release_event())

    assert item.cursor().shape() == Qt.CursorShape.OpenHandCursor


def test_deselecting_after_press_release_clears_cursor():
    document = _document_with_card()
    scene = QGraphicsScene()
    item = CardItem("c_1", document, undo_stack=QUndoStack())
    scene.addItem(item)
    item.mousePressEvent(_press_event())
    item.mouseReleaseEvent(_release_event())
    assert item.isSelected()

    item.setSelected(False)

    assert not item.hasCursor()


def test_entering_edit_mode_clears_grab_hand_cursor(qtbot):
    document = _document_with_card()
    stack = QUndoStack()
    item, scene = _editable_item(document, stack)
    item.setSelected(True)
    assert item.hasCursor()

    item.enter_edit_mode()

    assert not item.hasCursor()


def test_exiting_edit_mode_restores_grab_hand_cursor_when_selected(qtbot):
    document = _document_with_card()
    stack = QUndoStack()
    item, scene = _editable_item(document, stack)
    item.setSelected(True)
    item.enter_edit_mode()

    item._on_text_focus_out()

    assert item.cursor().shape() == Qt.CursorShape.OpenHandCursor


def test_link_mode_active_shows_cross_cursor_on_unselected_card():
    document = _document_with_card()
    scene = QGraphicsScene()
    item = CardItem("c_1", document, undo_stack=QUndoStack())
    scene.addItem(item)

    item.set_link_mode_active(True)

    assert item.cursor().shape() == Qt.CursorShape.CrossCursor


def test_link_mode_active_shows_cross_cursor_instead_of_grab_hand_on_selected_card():
    document = _document_with_card()
    scene = QGraphicsScene()
    item = CardItem("c_1", document, undo_stack=QUndoStack())
    scene.addItem(item)
    item.setSelected(True)
    assert item.cursor().shape() == Qt.CursorShape.OpenHandCursor

    item.set_link_mode_active(True)

    assert item.cursor().shape() == Qt.CursorShape.CrossCursor


def test_deactivating_link_mode_restores_grab_hand_when_selected():
    document = _document_with_card()
    scene = QGraphicsScene()
    item = CardItem("c_1", document, undo_stack=QUndoStack())
    scene.addItem(item)
    item.setSelected(True)
    item.set_link_mode_active(True)

    item.set_link_mode_active(False)

    assert item.cursor().shape() == Qt.CursorShape.OpenHandCursor


def test_deactivating_link_mode_clears_cursor_when_not_selected():
    document = _document_with_card()
    scene = QGraphicsScene()
    item = CardItem("c_1", document, undo_stack=QUndoStack())
    scene.addItem(item)
    item.set_link_mode_active(True)

    item.set_link_mode_active(False)

    assert not item.hasCursor()


def test_pressing_card_during_link_mode_does_not_show_closed_hand_cursor():
    document = _document_with_card()
    scene = QGraphicsScene()
    item = CardItem("c_1", document, undo_stack=QUndoStack())
    scene.addItem(item)
    item.set_link_mode_active(True)

    item.mousePressEvent(_press_event())

    assert item.cursor().shape() == Qt.CursorShape.CrossCursor


def test_set_dimmed_does_not_change_opacity(qtbot):
    document = _document_with_card()
    item = CardItem("c_1", document)

    item.set_dimmed(True)

    # Dimming must not use transparency — a translucent card would let a
    # link line drawn behind it show through at its center.
    assert item.opacity() == 1.0


def test_set_dimmed_is_idempotent_and_toggles_back(qtbot):
    document = _document_with_card()
    item = CardItem("c_1", document)

    item.set_dimmed(True)
    item.set_dimmed(True)  # should not raise or misbehave when unchanged
    assert item._dimmed is True

    item.set_dimmed(False)
    assert item._dimmed is False


def test_set_dimmed_dims_the_text_color(qtbot):
    document = _document_with_card()
    item = CardItem("c_1", document)
    normal_color = item._text_item.defaultTextColor()

    item.set_dimmed(True)

    dimmed_color = item._text_item.defaultTextColor()
    assert dimmed_color != normal_color
    assert dimmed_color == _dimmed_text_color(normal_color)


def test_set_dimmed_false_restores_normal_text_color(qtbot):
    document = _document_with_card()
    item = CardItem("c_1", document)
    normal_color = item._text_item.defaultTextColor()
    item.set_dimmed(True)

    item.set_dimmed(False)

    assert item._text_item.defaultTextColor() == normal_color


def test_set_dimmed_does_not_reset_text_content(qtbot):
    # set_dimmed must only touch color, not re-sync markdown from
    # card.text -- doing so would blow away an in-progress edit if a
    # search query changes while a card is being actively typed into.
    document = _document_with_card()
    item = CardItem("c_1", document)
    item._text_item.document().setPlainText("uncommitted edit in progress")

    item.set_dimmed(True)

    assert item._text_item.toPlainText() == "uncommitted edit in progress"


def test_tooltip_empty_when_no_tags(qtbot):
    document = _document_with_card()
    item = CardItem("c_1", document)
    assert item.toolTip() == ""


def test_tooltip_stays_empty_when_tags_present_but_disabled(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="hi", tags=["plot", "urgent"]))
    item = CardItem("c_1", document)
    assert item.toolTip() == ""


def test_tooltip_shows_tags_when_enabled(qtbot, monkeypatch):
    monkeypatch.setattr("indexcards.canvas.card_item.TAGS_ENABLED", True)
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="hi", tags=["plot", "urgent"]))
    item = CardItem("c_1", document)
    assert item.toolTip() == "plot, urgent"


def test_tooltip_updates_on_refresh_when_enabled(qtbot, monkeypatch):
    monkeypatch.setattr("indexcards.canvas.card_item.TAGS_ENABLED", True)
    document = _document_with_card()
    item = CardItem("c_1", document)
    assert item.toolTip() == ""

    document.set_card_tags("c_1", ["new-tag"])
    item.refresh()

    assert item.toolTip() == "new-tag"


def _render_card_image(item: CardItem) -> QImage:
    image = QImage(200, 200, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        item.paint(painter, None)
    finally:
        painter.end()
    return image


def _render_card(item: CardItem) -> None:
    _render_card_image(item)


def test_paint_does_not_crash_without_tags(qtbot):
    document = _document_with_card()
    item = CardItem("c_1", document)
    _render_card(item)  # must not raise


def test_paint_does_not_crash_with_tags(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="hi", tags=["plot"]))
    item = CardItem("c_1", document)
    _render_card(item)  # must not raise


def test_orphaned_card_renders_differently_from_a_non_orphaned_one_of_the_same_color():
    plain_document = _document_with_card()
    plain_item = CardItem("c_1", plain_document)
    plain_image = _render_card_image(plain_item)

    orphaned_document = _document_with_card()
    orphaned_document.get_slot("slot_white").orphaned = True
    orphaned_item = CardItem("c_1", orphaned_document)
    orphaned_image = _render_card_image(orphaned_item)

    differs = any(
        plain_image.pixelColor(x, y) != orphaned_image.pixelColor(x, y)
        for x in range(plain_image.width())
        for y in range(plain_image.height())
    )
    assert differs


def _simulate_typing(item: CardItem, text: str) -> None:
    """Replaces all content via QTextCursor, which (unlike setPlainText)
    marks the document modified — the same way real keystrokes would."""
    cursor = item._text_item.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    cursor.insertText(text)


def _editable_item(document: Document, stack: QUndoStack) -> tuple[CardItem, QGraphicsScene]:
    # Returns (item, scene) — the caller must keep scene referenced for as
    # long as item is used, or Python GC'ing the scene wrapper deletes the
    # underlying C++ item along with it.
    scene = QGraphicsScene()
    item = CardItem("c_1", document, undo_stack=stack)
    scene.addItem(item)
    return item, scene


def test_enter_edit_mode_selects_all_text_and_disables_dragging():
    document = _document_with_card()
    stack = QUndoStack()
    item, scene = _editable_item(document, stack)

    item.enter_edit_mode()

    assert item._editing is True
    assert not (item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
    assert item._text_item.textCursor().hasSelection()


def test_enter_edit_mode_without_undo_stack_is_noop():
    document = _document_with_card()
    item = CardItem("c_1", document)

    item.enter_edit_mode()

    assert item._editing is False


def test_double_click_enters_edit_mode():
    document = _document_with_card()
    stack = QUndoStack()
    item, scene = _editable_item(document, stack)

    press = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMouseDoubleClick)
    item.mouseDoubleClickEvent(press)

    assert item._editing is True


def test_focus_out_commits_text_change():
    document = _document_with_card()
    stack = QUndoStack()
    item, scene = _editable_item(document, stack)

    item.enter_edit_mode()
    _simulate_typing(item, "new content")
    item._on_text_focus_out()

    assert item._editing is False
    assert document.get_card("c_1").text == "new content"
    assert stack.canUndo()

    stack.undo()
    assert document.get_card("c_1").text == "**Bold** idea"


def test_typing_past_char_limit_is_blocked_live():
    document = _document_with_card()
    stack = QUndoStack()
    item, scene = _editable_item(document, stack)
    item.enter_edit_mode()

    _simulate_typing(item, "a" * (MAX_TEXT_LENGTH + 40))

    assert len(item._text_item.toPlainText()) == MAX_TEXT_LENGTH


def test_typing_up_to_char_limit_is_not_truncated():
    document = _document_with_card()
    stack = QUndoStack()
    item, scene = _editable_item(document, stack)
    item.enter_edit_mode()

    _simulate_typing(item, "a" * MAX_TEXT_LENGTH)

    assert len(item._text_item.toPlainText()) == MAX_TEXT_LENGTH


def test_typing_further_at_char_limit_still_blocked():
    document = _document_with_card()
    stack = QUndoStack()
    item, scene = _editable_item(document, stack)
    item.enter_edit_mode()
    _simulate_typing(item, "a" * MAX_TEXT_LENGTH)

    cursor = item._text_item.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertText("bcdef")

    assert item._text_item.toPlainText() == "a" * MAX_TEXT_LENGTH


def test_char_limit_not_enforced_outside_edit_mode():
    # Loading/refreshing a card whose stored text is already over the
    # limit (e.g. from a file saved before this limit existed) must not
    # get silently clipped just by being displayed.
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="a" * (MAX_TEXT_LENGTH + 40)))
    item = CardItem("c_1", document)

    assert len(item._text_item.toPlainText()) == MAX_TEXT_LENGTH + 40


def test_char_limit_stops_enforcing_after_exiting_edit_mode():
    document = _document_with_card()
    stack = QUndoStack()
    item, scene = _editable_item(document, stack)
    item.enter_edit_mode()
    item._on_text_focus_out()

    # Directly mutate the (no-longer-monitored) document past the limit —
    # simulates the card being reloaded/refreshed with an over-limit value
    # after the edit session that connected the limiter has ended.
    item._text_item.document().setPlainText("a" * (MAX_TEXT_LENGTH + 40))

    assert len(item._text_item.toPlainText()) == MAX_TEXT_LENGTH + 40


def test_active_window_focus_reason_does_not_exit_edit_mode():
    # Regression: a QGraphicsView losing/regaining OS-level "active
    # window" status (e.g. macOS completing a delayed activation
    # handshake right after a double-click creates a card and enters
    # edit mode — often surfacing on the very next mouse move) delivers
    # a real focusOutEvent here with reason=ActiveWindowFocusReason, not
    # a genuine "user backed out." That must not commit/exit editing —
    # only OtherFocusReason (click elsewhere, Escape) should.
    document = _document_with_card()
    stack = QUndoStack()
    item, scene = _editable_item(document, stack)
    item.enter_edit_mode()

    item._text_item.focusOutEvent(
        QFocusEvent(QEvent.Type.FocusOut, Qt.FocusReason.ActiveWindowFocusReason)
    )

    assert item._editing is True
    assert item._text_item.textInteractionFlags() & Qt.TextInteractionFlag.TextEditorInteraction


def test_other_focus_reason_still_exits_edit_mode():
    document = _document_with_card()
    stack = QUndoStack()
    item, scene = _editable_item(document, stack)
    item.enter_edit_mode()

    item._text_item.focusOutEvent(
        QFocusEvent(QEvent.Type.FocusOut, Qt.FocusReason.OtherFocusReason)
    )

    assert item._editing is False


def test_text_item_bounding_rect_spans_full_card_not_just_rendered_text():
    # Regression: while a card holds only short text (e.g. the default
    # "New Card 1"), QGraphicsTextItem's own natural bounding rect only
    # covers a thin sliver near the top of the card. A press anywhere
    # else in the card — still well within it, nowhere near "clicking
    # away" — would otherwise miss this child item and land on the
    # parent CardItem instead, which (via Qt's own scene-level
    # mouse-press focus handling, before CardItem.mousePressEvent even
    # runs) spuriously ends editing. The text item's bounding rect must
    # cover the card's entire (0,0)-(width,height) area, accounting for
    # its own (_TEXT_MARGIN, _TEXT_MARGIN) offset from the card's origin.
    document = _document_with_card()  # short text: "**Bold** idea"
    item = CardItem("c_1", document)

    width, height = DEFAULT_CARD_SIZE
    card_rect_in_text_item_local_coords = QRectF(
        -_TEXT_MARGIN, -_TEXT_MARGIN, width, height
    )
    assert item._text_item.boundingRect().contains(card_rect_in_text_item_local_coords)


def test_press_anywhere_in_card_while_editing_does_not_end_edit_mode():
    document = _document_with_card()
    stack = QUndoStack()
    scene = QGraphicsScene()
    item = CardItem("c_1", document, undo_stack=stack)
    scene.addItem(item)
    item.enter_edit_mode()

    width, height = DEFAULT_CARD_SIZE
    for local_point in (
        QPointF(1, 1),  # top-left corner
        QPointF(width - 1, 1),  # top-right corner
        QPointF(1, height - 1),  # bottom-left corner
        QPointF(width - 1, height - 1),  # bottom-right corner
        QPointF(width / 2, height / 2),  # center
    ):
        target = item.mapToItem(item._text_item, local_point)
        event = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMousePress)
        event.setPos(target)
        event.setButton(Qt.MouseButton.LeftButton)
        item._text_item.mousePressEvent(event)
        assert item._editing is True, f"editing ended after a press at {local_point}"


def test_escape_commits_text_change(monkeypatch):
    # A headless test has no real window focus, so clearFocus() wouldn't
    # actually fire focusOutEvent — patch it to do what it does in a real,
    # focused view, the same way the old dock tests synthesized a
    # QFocusEvent directly rather than relying on real widget focus.
    def fake_clear_focus(self) -> None:
        self.focusOutEvent(QFocusEvent(QEvent.Type.FocusOut, Qt.FocusReason.OtherFocusReason))

    monkeypatch.setattr(_CardTextItem, "clearFocus", fake_clear_focus)

    document = _document_with_card()
    stack = QUndoStack()
    item, scene = _editable_item(document, stack)

    item.enter_edit_mode()
    _simulate_typing(item, "typed then escaped")

    escape_event = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier
    )
    item._text_item.keyPressEvent(escape_event)

    assert item._editing is False
    assert document.get_card("c_1").text == "typed then escaped"


def test_focus_out_without_change_does_not_push_command():
    document = _document_with_card()
    stack = QUndoStack()
    item, scene = _editable_item(document, stack)

    item.enter_edit_mode()
    item._on_text_focus_out()

    assert stack.canUndo() is False


def test_commit_text_after_card_removed_does_not_raise():
    document = _document_with_card()
    stack = QUndoStack()
    item, scene = _editable_item(document, stack)

    item.enter_edit_mode()
    _simulate_typing(item, "orphaned edit")
    document.remove_card("c_1")

    item._on_text_focus_out()  # must not raise

    assert stack.canUndo() is False


def test_toggle_bold_via_shortcut_changes_current_format():
    document = _document_with_card()
    stack = QUndoStack()
    item, scene = _editable_item(document, stack)
    item.enter_edit_mode()

    assert item._text_item.textCursor().charFormat().fontWeight() != QFont.Weight.Bold
    item._text_item._toggle_bold()
    assert item._text_item.textCursor().charFormat().fontWeight() == QFont.Weight.Bold
    item._text_item._toggle_bold()
    assert item._text_item.textCursor().charFormat().fontWeight() != QFont.Weight.Bold


def test_toggle_italic_via_shortcut_changes_current_format():
    document = _document_with_card()
    stack = QUndoStack()
    item, scene = _editable_item(document, stack)
    item.enter_edit_mode()

    assert item._text_item.textCursor().charFormat().fontItalic() is False
    item._text_item._toggle_italic()
    assert item._text_item.textCursor().charFormat().fontItalic() is True


def test_set_color_pushes_change_color_command():
    document = _document_with_card()
    document.set_card_color_slot("c_1", "slot_white")
    stack = QUndoStack()
    item, scene = _editable_item(document, stack)

    item._set_color_slot("slot_blue")

    assert document.get_card("c_1").color_slot == "slot_blue"
    assert stack.canUndo()

    stack.undo()
    assert document.get_card("c_1").color_slot == "slot_white"


def test_set_color_same_value_does_not_push_command():
    document = _document_with_card()
    document.set_card_color_slot("c_1", "slot_white")
    stack = QUndoStack()
    item, scene = _editable_item(document, stack)

    item._set_color_slot("slot_white")

    assert stack.canUndo() is False


def test_text_color_auto_picks_black_on_light_slot():
    document = _document_with_card()
    item = CardItem("c_1", document)
    assert item._text_item.defaultTextColor() == QColor("#000000")


def test_text_color_auto_picks_white_on_dark_slot():
    document = _document_with_card()
    document.theme.slots.append(Slot(id="slot_dark", label="Dark", hex="#101010"))
    document.set_card_color_slot("c_1", "slot_dark")
    item = CardItem("c_1", document)
    assert item._text_item.defaultTextColor() == QColor("#ffffff")


def test_text_color_respects_explicit_override():
    document = _document_with_card()
    document.get_slot("slot_white").text_color = "#ff0000"
    item = CardItem("c_1", document)
    assert item._text_item.defaultTextColor() == QColor("#ff0000")


def test_text_color_updates_on_refresh_after_color_slot_change():
    document = _document_with_card()
    document.theme.slots.append(Slot(id="slot_dark", label="Dark", hex="#101010"))
    item = CardItem("c_1", document)
    assert item._text_item.defaultTextColor() == QColor("#000000")

    document.set_card_color_slot("c_1", "slot_dark")
    item.refresh()

    assert item._text_item.defaultTextColor() == QColor("#ffffff")


def test_edit_tags_via_dialog_pushes_change_tags_command(monkeypatch):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="hi", tags=["plot"]))
    stack = QUndoStack()
    item, scene = _editable_item(document, stack)

    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *a, **k: ("plot, urgent", True))
    )
    item._edit_tags_via_dialog()

    assert document.get_card("c_1").tags == ["plot", "urgent"]
    assert stack.canUndo()

    stack.undo()
    assert document.get_card("c_1").tags == ["plot"]


def test_edit_tags_via_dialog_cancelled_does_not_push_command(monkeypatch):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="hi", tags=["plot"]))
    stack = QUndoStack()
    item, scene = _editable_item(document, stack)

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("", False)))
    item._edit_tags_via_dialog()

    assert stack.canUndo() is False
    assert document.get_card("c_1").tags == ["plot"]


def _context_menu_action_texts(item: CardItem) -> list[str]:
    menu, *_rest = item._build_context_menu()
    return [action.text() for action in menu.actions()]


def test_context_menu_omits_edit_tags_by_default():
    document = _document_with_card()
    stack = QUndoStack()
    item, scene = _editable_item(document, stack)

    assert "Edit Tags…" not in _context_menu_action_texts(item)


def test_context_menu_includes_edit_tags_when_enabled(monkeypatch):
    monkeypatch.setattr("indexcards.canvas.card_item.TAGS_ENABLED", True)
    document = _document_with_card()
    stack = QUndoStack()
    item, scene = _editable_item(document, stack)

    assert "Edit Tags…" in _context_menu_action_texts(item)


def test_context_menu_color_actions_have_swatch_icons():
    document = _document_with_card()
    stack = QUndoStack()
    item, scene = _editable_item(document, stack)

    _menu, _edit_tags_action, _select_linked_action, _pin_action, color_actions, *_rest = (
        item._build_context_menu()
    )

    assert color_actions  # sanity: PALETTE isn't empty
    for action in color_actions:
        assert not action.icon().isNull()


def test_context_menu_select_linked_disabled_without_links():
    document = _document_with_card()
    stack = QUndoStack()
    item, scene = _editable_item(document, stack)

    _menu, _edit_tags_action, select_linked_action, _pin_action, *_rest = (
        item._build_context_menu()
    )

    assert select_linked_action.text() == "Select Linked"
    assert not select_linked_action.isEnabled()


def test_context_menu_select_linked_enabled_with_links():
    document = _document_with_card()
    document.add_card(Card(id="c_2", text="other", x=200.0, y=200.0))
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    stack = QUndoStack()
    item, scene = _editable_item(document, stack)

    _menu, _edit_tags_action, select_linked_action, _pin_action, *_rest = (
        item._build_context_menu()
    )

    assert select_linked_action.isEnabled()


def test_context_menu_pin_action_reads_pin_card_when_unpinned():
    document = _document_with_card()
    stack = QUndoStack()
    item, scene = _editable_item(document, stack)

    _menu, _edit_tags_action, _select_linked_action, pin_action, *_rest = (
        item._build_context_menu()
    )

    assert pin_action.text() == "Pin Card"


def test_context_menu_pin_action_reads_unpin_card_when_pinned():
    document = _document_with_card()
    document.set_card_pinned("c_1", True)
    stack = QUndoStack()
    item, scene = _editable_item(document, stack)

    _menu, _edit_tags_action, _select_linked_action, pin_action, *_rest = (
        item._build_context_menu()
    )

    assert pin_action.text() == "Unpin Card"


def test_context_menu_pin_action_reads_plural_for_multi_selection():
    document = _document_with_card()
    document.add_card(Card(id="c_2", text="other", x=200.0, y=0.0))
    stack = QUndoStack()
    scene = QGraphicsScene()
    item = CardItem("c_1", document, undo_stack=stack)
    item_2 = CardItem("c_2", document, undo_stack=stack)
    scene.addItem(item)
    scene.addItem(item_2)
    item.setSelected(True)
    item_2.setSelected(True)

    _menu, _edit_tags_action, _select_linked_action, pin_action, *_rest = (
        item._build_context_menu()
    )

    assert pin_action.text() == "Pin Cards"


def test_selection_scoped_card_ids_is_just_this_card_when_unselected():
    document = _document_with_card()
    document.add_card(Card(id="c_2", text="other", x=200.0, y=0.0))
    scene = QGraphicsScene()
    item = CardItem("c_1", document, undo_stack=QUndoStack())
    item_2 = CardItem("c_2", document, undo_stack=QUndoStack())
    scene.addItem(item)
    scene.addItem(item_2)
    item_2.setSelected(True)  # a different card is selected, not this one

    assert item._selection_scoped_card_ids() == ["c_1"]


def test_selection_scoped_card_ids_is_whole_selection_when_part_of_it():
    document = _document_with_card()
    document.add_card(Card(id="c_2", text="other", x=200.0, y=0.0))
    scene = QGraphicsScene()
    item = CardItem("c_1", document, undo_stack=QUndoStack())
    item_2 = CardItem("c_2", document, undo_stack=QUndoStack())
    scene.addItem(item)
    scene.addItem(item_2)
    item.setSelected(True)
    item_2.setSelected(True)

    assert set(item._selection_scoped_card_ids()) == {"c_1", "c_2"}


def test_toggle_pin_pins_mixed_selection_entirely():
    document = _document_with_card()
    document.add_card(Card(id="c_2", text="other", x=200.0, y=0.0, pinned=True))
    stack = QUndoStack()
    scene = QGraphicsScene()
    item = CardItem("c_1", document, undo_stack=stack)
    item_2 = CardItem("c_2", document, undo_stack=stack)
    scene.addItem(item)
    scene.addItem(item_2)
    item.setSelected(True)
    item_2.setSelected(True)

    item._toggle_pin()

    assert document.get_card("c_1").pinned is True
    assert document.get_card("c_2").pinned is True


def test_toggle_pin_unpins_when_all_already_pinned():
    document = _document_with_card()
    document.set_card_pinned("c_1", True)
    stack = QUndoStack()
    item, scene = _editable_item(document, stack)

    item._toggle_pin()

    assert document.get_card("c_1").pinned is False


def test_pin_action_is_distinct_from_other_context_menu_actions():
    document = _document_with_card()
    stack = QUndoStack()
    item, scene = _editable_item(document, stack)

    _menu, edit_tags_action, select_linked_action, pin_action, color_actions, *_rest = (
        item._build_context_menu()
    )

    assert pin_action is not select_linked_action
    assert pin_action is not edit_tags_action
    assert pin_action not in color_actions


def test_paint_does_not_crash_when_pinned(qtbot):
    document = _document_with_card()
    document.set_card_pinned("c_1", True)
    item = CardItem("c_1", document)
    _render_card(item)  # must not raise


def test_select_linked_graph_selects_connected_component():
    document = _document_with_card()
    document.add_card(Card(id="c_2", text="middle", x=200.0, y=0.0))
    document.add_card(Card(id="c_3", text="far", x=400.0, y=0.0))
    document.add_card(Card(id="c_4", text="unrelated", x=600.0, y=0.0))
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    document.add_link(Link(id="l_2", source="c_2", target="c_3"))
    scene = QGraphicsScene()
    items = {}
    for card_id in ("c_1", "c_2", "c_3", "c_4"):
        card_item = CardItem(card_id, document)
        scene.addItem(card_item)
        items[card_id] = card_item

    items["c_1"].select_linked_graph()

    assert items["c_1"].isSelected()
    assert items["c_2"].isSelected()
    assert items["c_3"].isSelected()
    assert not items["c_4"].isSelected()


def test_select_linked_graph_also_selects_the_links_in_the_component():
    from indexcards.canvas.link_item import LinkItem

    document = _document_with_card()
    document.add_card(Card(id="c_2", text="middle", x=200.0, y=0.0))
    document.add_card(Card(id="c_3", text="far", x=400.0, y=0.0))
    document.add_card(Card(id="c_4", text="unrelated", x=600.0, y=0.0))
    document.add_card(Card(id="c_5", text="also unrelated", x=800.0, y=0.0))
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    document.add_link(Link(id="l_2", source="c_2", target="c_3"))
    document.add_link(Link(id="l_unrelated", source="c_4", target="c_5"))
    scene = QGraphicsScene()
    card_items = {}
    for card_id in ("c_1", "c_2", "c_3", "c_4", "c_5"):
        card_item = CardItem(card_id, document)
        scene.addItem(card_item)
        card_items[card_id] = card_item
    link_1 = LinkItem("l_1", card_items["c_1"], card_items["c_2"], document)
    link_2 = LinkItem("l_2", card_items["c_2"], card_items["c_3"], document)
    link_unrelated = LinkItem("l_unrelated", card_items["c_4"], card_items["c_5"], document)
    for link_item in (link_1, link_2, link_unrelated):
        scene.addItem(link_item)

    card_items["c_1"].select_linked_graph()

    assert link_1.isSelected()
    assert link_2.isSelected()
    assert not link_unrelated.isSelected()


def test_select_linked_graph_replaces_existing_selection_by_default():
    document = _document_with_card()
    document.add_card(Card(id="c_2", text="other", x=200.0, y=0.0))
    scene = QGraphicsScene()
    item_1 = CardItem("c_1", document)
    item_2 = CardItem("c_2", document)
    scene.addItem(item_1)
    scene.addItem(item_2)
    item_2.setSelected(True)

    item_1.select_linked_graph()

    assert item_1.isSelected()
    assert not item_2.isSelected()


def test_select_linked_graph_union_keeps_existing_selection():
    document = _document_with_card()
    document.add_card(Card(id="c_2", text="other", x=200.0, y=0.0))
    scene = QGraphicsScene()
    item_1 = CardItem("c_1", document)
    item_2 = CardItem("c_2", document)
    scene.addItem(item_1)
    scene.addItem(item_2)
    item_2.setSelected(True)

    item_1.select_linked_graph(union=True)

    assert item_1.isSelected()
    assert item_2.isSelected()


def test_select_linked_graph_without_scene_is_noop():
    document = _document_with_card()
    item = CardItem("c_1", document)

    item.select_linked_graph()  # must not raise


def test_context_menu_add_to_stack_submenu_lists_new_stack_first():
    document = _document_with_card()
    stack = QUndoStack()
    item, _scene = _editable_item(document, stack)

    _menu, _e, _s, _p, _c, new_stack_action, stack_actions, _r = item._build_context_menu()

    assert new_stack_action.text() == "New Stack..."
    assert stack_actions == {}


def test_context_menu_add_to_stack_submenu_lists_existing_stacks():
    document = _document_with_card()
    document.add_stack(Stack(id="s_1", label="Chapter 1"))
    stack = QUndoStack()
    item, _scene = _editable_item(document, stack)

    _menu, _e, _s, _p, _c, _new_stack_action, stack_actions, _r = item._build_context_menu()

    assert list(stack_actions.values()) == ["s_1"]
    (action,) = stack_actions.keys()
    assert action.text() == "Chapter 1"


def test_context_menu_add_to_stack_unlabeled_stack_shows_count():
    document = _document_with_card()
    document.add_card(Card(id="c_2", text="other", x=200.0, y=0.0, stack_id="s_1"))
    document.add_stack(Stack(id="s_1", card_ids=["c_2"]))
    stack = QUndoStack()
    item, _scene = _editable_item(document, stack)

    _menu, _e, _s, _p, _c, _new_stack_action, stack_actions, _r = item._build_context_menu()

    (action,) = stack_actions.keys()
    assert action.text() == "Stack (1 cards)"


def test_context_menu_add_to_stack_submenu_hidden_when_card_already_stacked():
    document = _document_with_card()
    document.get_card("c_1").stack_id = "s_1"
    document.add_stack(Stack(id="s_1", card_ids=["c_1"]))
    document.add_stack(Stack(id="s_2", label="Other Stack"))
    stack = QUndoStack()
    item, _scene = _editable_item(document, stack)

    _menu, _e, _s, _p, _c, new_stack_action, stack_actions, _r = item._build_context_menu()

    assert new_stack_action is None
    assert stack_actions == {}


def test_context_menu_stacked_card_offers_remove_from_stack_not_pin_or_select_linked():
    document = _document_with_card()
    document.get_card("c_1").stack_id = "s_1"
    document.add_stack(Stack(id="s_1", card_ids=["c_1"]))
    stack = QUndoStack()
    item, _scene = _editable_item(document, stack)

    (
        menu,
        _edit_tags_action,
        select_linked_action,
        pin_action,
        _color_actions,
        _new_stack_action,
        _stack_actions,
        remove_from_stack_action,
    ) = item._build_context_menu()

    assert select_linked_action is None
    assert pin_action is None
    assert remove_from_stack_action is not None
    assert remove_from_stack_action.text() == "Remove from Stack"
    action_texts = [action.text() for action in menu.actions()]
    assert "Select Linked" not in action_texts
    assert "Pin Card" not in action_texts
    assert "Unpin Card" not in action_texts


def test_context_menu_unstacked_card_has_no_remove_from_stack():
    document = _document_with_card()
    stack = QUndoStack()
    item, _scene = _editable_item(document, stack)

    *_rest, remove_from_stack_action = item._build_context_menu()

    assert remove_from_stack_action is None


def test_remove_from_stack_calls_eject_card_on_owning_overlay():
    document = _document_with_card()
    document.get_card("c_1").stack_id = "s_1"
    document.add_stack(Stack(id="s_1", card_ids=["c_1"]))
    stack = QUndoStack()
    item = CardItem("c_1", document, undo_stack=stack)

    calls = []

    class _FakeOverlay:
        def eject_card(self, card_id):
            calls.append(card_id)

    item._overlay = _FakeOverlay()
    item._remove_from_stack()

    assert calls == ["c_1"]


def test_create_new_stack_via_menu_single_card(monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Chapter 1", True)))
    document = _document_with_card()
    stack = QUndoStack()
    item, _scene = _editable_item(document, stack)

    item._create_new_stack_via_menu()

    assert document.get_card("c_1").stack_id is not None
    new_stack_id = document.get_card("c_1").stack_id
    assert document.get_stack(new_stack_id).label == "Chapter 1"
    assert document.get_stack(new_stack_id).card_ids == ["c_1"]
    # New stack lands where the card was (_document_with_card places c_1
    # at (50.0, 75.0)).
    assert (document.get_stack(new_stack_id).x, document.get_stack(new_stack_id).y) == (50.0, 75.0)


def test_create_new_stack_via_menu_multi_selection_includes_all_selected(monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("", True)))
    document = _document_with_card()
    document.add_card(Card(id="c_2", text="other", x=200.0, y=0.0))
    stack = QUndoStack()
    scene = QGraphicsScene()
    item = CardItem("c_1", document, undo_stack=stack)
    item_2 = CardItem("c_2", document, undo_stack=stack)
    scene.addItem(item)
    scene.addItem(item_2)
    item.setSelected(True)
    item_2.setSelected(True)

    item._create_new_stack_via_menu()

    assert document.get_card("c_1").stack_id == document.get_card("c_2").stack_id
    new_stack_id = document.get_card("c_1").stack_id
    assert set(document.get_stack(new_stack_id).card_ids) == {"c_1", "c_2"}


def test_add_to_existing_stack_via_menu():
    document = _document_with_card()
    document.add_stack(Stack(id="s_1"))
    stack = QUndoStack()
    item, _scene = _editable_item(document, stack)

    item._add_to_existing_stack("s_1")

    assert document.get_card("c_1").stack_id == "s_1"
    assert document.get_stack("s_1").card_ids == ["c_1"]
