from PySide6.QtCore import QEvent, Qt
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
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsSceneMouseEvent,
    QInputDialog,
)

from indexcards.canvas.card_item import _CORNER_RADIUS, CardItem, _CardTextItem, _desaturated
from indexcards.models.card import DEFAULT_CARD_SIZE, Card
from indexcards.models.document import Document


def test_desaturated_removes_saturation_but_keeps_lightness():
    original = QColor("#F6E27A")  # a saturated yellow
    result = _desaturated(original)

    assert result.saturation() == 0
    assert result.value() == original.value()


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


def _render_card(item: CardItem) -> None:
    image = QImage(200, 200, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    try:
        item.paint(painter, None)
    finally:
        painter.end()


def test_paint_does_not_crash_without_tags(qtbot):
    document = _document_with_card()
    item = CardItem("c_1", document)
    _render_card(item)  # must not raise


def test_paint_does_not_crash_with_tags(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="hi", tags=["plot"]))
    item = CardItem("c_1", document)
    _render_card(item)  # must not raise


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
    document.set_card_color("c_1", "#FFFFFF")
    stack = QUndoStack()
    item, scene = _editable_item(document, stack)

    item._set_color("#A8D8F0")

    assert document.get_card("c_1").color == "#A8D8F0"
    assert stack.canUndo()

    stack.undo()
    assert document.get_card("c_1").color == "#FFFFFF"


def test_set_color_same_value_does_not_push_command():
    document = _document_with_card()
    document.set_card_color("c_1", "#FFFFFF")
    stack = QUndoStack()
    item, scene = _editable_item(document, stack)

    item._set_color("#FFFFFF")

    assert stack.canUndo() is False


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
    menu, _edit_tags_action, _color_actions = item._build_context_menu()
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
