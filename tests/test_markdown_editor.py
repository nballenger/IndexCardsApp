from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QFocusEvent, QFont, QTextCursor, QUndoStack
from PySide6.QtWidgets import QTextEdit

from indexcards.models.card import Card
from indexcards.models.document import Document
from indexcards.widgets.markdown_editor import MarkdownEditorWidget


def _document_with_card(text: str = "old text") -> Document:
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text=text))
    return document


def _simulate_typing(text_edit: QTextEdit, text: str) -> None:
    """Replaces all content via QTextCursor, which (unlike setPlainText)
    marks the document modified — the same way real keystrokes would."""
    cursor = text_edit.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    cursor.insertText(text)


def test_set_card_loads_text_and_enables_editor(qtbot):
    document = _document_with_card("Hello **world**")
    editor = MarkdownEditorWidget()
    qtbot.addWidget(editor)

    editor.set_card(document, None, "c_1")

    assert editor.text_edit.isEnabled()
    assert editor.text_edit.toPlainText() == "Hello world"


def test_set_card_none_disables_editor(qtbot):
    editor = MarkdownEditorWidget()
    qtbot.addWidget(editor)

    editor.set_card(None, None, None)

    assert not editor.text_edit.isEnabled()
    assert not editor.bold_button.isEnabled()


def test_commit_noop_when_not_modified(qtbot):
    document = _document_with_card()
    stack = QUndoStack()
    editor = MarkdownEditorWidget()
    qtbot.addWidget(editor)
    editor.set_card(document, stack, "c_1")

    editor._commit()

    assert stack.canUndo() is False


def test_commit_pushes_command_when_modified(qtbot):
    document = _document_with_card()
    stack = QUndoStack()
    editor = MarkdownEditorWidget()
    qtbot.addWidget(editor)
    editor.set_card(document, stack, "c_1")

    _simulate_typing(editor.text_edit, "new content")
    assert editor.text_edit.document().isModified()

    editor._commit()

    assert stack.canUndo()
    assert "new content" in document.get_card("c_1").text

    stack.undo()
    assert document.get_card("c_1").text == "old text"


def test_focus_out_triggers_commit(qtbot):
    document = _document_with_card()
    stack = QUndoStack()
    editor = MarkdownEditorWidget()
    qtbot.addWidget(editor)
    editor.set_card(document, stack, "c_1")

    _simulate_typing(editor.text_edit, "typed via focus-out")
    focus_out = QFocusEvent(QEvent.Type.FocusOut, Qt.FocusReason.OtherFocusReason)
    editor.text_edit.focusOutEvent(focus_out)

    assert stack.canUndo()
    assert "typed via focus-out" in document.get_card("c_1").text


def test_toggle_bold_changes_current_format(qtbot):
    document = _document_with_card()
    editor = MarkdownEditorWidget()
    qtbot.addWidget(editor)
    editor.set_card(document, QUndoStack(), "c_1")

    assert editor.text_edit.fontWeight() != QFont.Weight.Bold
    editor._toggle_bold()
    assert editor.text_edit.fontWeight() == QFont.Weight.Bold
    editor._toggle_bold()
    assert editor.text_edit.fontWeight() != QFont.Weight.Bold


def test_toggle_italic_changes_current_format(qtbot):
    document = _document_with_card()
    editor = MarkdownEditorWidget()
    qtbot.addWidget(editor)
    editor.set_card(document, QUndoStack(), "c_1")

    assert editor.text_edit.fontItalic() is False
    editor._toggle_italic()
    assert editor.text_edit.fontItalic() is True


def test_card_removed_clears_and_disables_editor(qtbot):
    document = _document_with_card()
    editor = MarkdownEditorWidget()
    qtbot.addWidget(editor)
    editor.set_card(document, QUndoStack(), "c_1")

    document.remove_card("c_1")

    assert not editor.text_edit.isEnabled()


def test_external_text_change_refreshes_editor_when_idle(qtbot):
    document = _document_with_card()
    editor = MarkdownEditorWidget()
    qtbot.addWidget(editor)
    editor.set_card(document, QUndoStack(), "c_1")

    document.set_card_text("c_1", "changed elsewhere")

    assert "changed elsewhere" in editor.text_edit.toPlainText()


def test_external_text_change_does_not_clobber_in_progress_edit(qtbot):
    document = _document_with_card()
    editor = MarkdownEditorWidget()
    qtbot.addWidget(editor)
    editor.set_card(document, QUndoStack(), "c_1")

    _simulate_typing(editor.text_edit, "still typing")
    assert editor.text_edit.document().isModified()

    document.set_card_text("c_1", "changed elsewhere")

    assert editor.text_edit.toPlainText() == "still typing"


def test_switching_cards_commits_pending_edit_on_previous_card(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="first"))
    document.add_card(Card(id="c_2", text="second"))
    stack = QUndoStack()
    editor = MarkdownEditorWidget()
    qtbot.addWidget(editor)

    editor.set_card(document, stack, "c_1")
    _simulate_typing(editor.text_edit, "edited first")

    editor.set_card(document, stack, "c_2")

    assert "edited first" in document.get_card("c_1").text
    assert editor.text_edit.toPlainText() == "second"


def test_set_card_loads_tags_and_color(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="hi", color="#A8D8F0", tags=["plot", "urgent"]))
    editor = MarkdownEditorWidget()
    qtbot.addWidget(editor)

    editor.set_card(document, None, "c_1")

    assert editor.tags_edit.text() == "plot, urgent"
    assert editor.color_combo.currentData() == "#A8D8F0"
    assert editor.tags_edit.isEnabled()
    assert editor.color_combo.isEnabled()


def test_set_card_none_disables_metadata_fields(qtbot):
    editor = MarkdownEditorWidget()
    qtbot.addWidget(editor)

    editor.set_card(None, None, None)

    assert not editor.tags_edit.isEnabled()
    assert not editor.color_combo.isEnabled()
    assert editor.tags_edit.text() == ""


def test_editing_tags_pushes_change_tags_command(qtbot):
    document = _document_with_card()
    document.set_card_tags("c_1", [])
    stack = QUndoStack()
    editor = MarkdownEditorWidget()
    qtbot.addWidget(editor)
    editor.set_card(document, stack, "c_1")

    editor.tags_edit.clear()
    qtbot.keyClicks(editor.tags_edit, "plot, urgent")
    editor.tags_edit.editingFinished.emit()

    assert document.get_card("c_1").tags == ["plot", "urgent"]
    assert stack.canUndo()

    stack.undo()
    assert document.get_card("c_1").tags == []


def test_tags_editing_finished_without_change_does_not_push_command(qtbot):
    document = _document_with_card()
    document.set_card_tags("c_1", ["plot"])
    stack = QUndoStack()
    editor = MarkdownEditorWidget()
    qtbot.addWidget(editor)
    editor.set_card(document, stack, "c_1")

    editor.tags_edit.editingFinished.emit()  # no edit made

    assert stack.canUndo() is False


def test_selecting_color_pushes_change_color_command(qtbot):
    document = _document_with_card()
    document.set_card_color("c_1", "#FFFFFF")
    stack = QUndoStack()
    editor = MarkdownEditorWidget()
    qtbot.addWidget(editor)
    editor.set_card(document, stack, "c_1")

    target_index = editor.color_combo.findData("#A8D8F0")
    editor.color_combo.setCurrentIndex(target_index)

    assert document.get_card("c_1").color == "#A8D8F0"
    assert stack.canUndo()

    stack.undo()
    assert document.get_card("c_1").color == "#FFFFFF"


def test_loading_color_does_not_push_spurious_command(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="a", color="#A8D8F0"))
    document.add_card(Card(id="c_2", text="b", color="#B7E4C7"))
    stack = QUndoStack()
    editor = MarkdownEditorWidget()
    qtbot.addWidget(editor)
    editor.set_card(document, stack, "c_1")

    editor.set_card(document, stack, "c_2")  # loading c_2's color must not push

    assert stack.canUndo() is False


def test_switching_cards_after_delete_does_not_crash(qtbot):
    # Regression: _commit_tags() used to read self._card_id unconditionally,
    # which could be the just-deleted card's id when set_card() is called
    # reentrantly during a cascading delete (same class of bug as the M9
    # canvas-selection fix, but for the new tags commit path).
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="first"))
    document.add_card(Card(id="c_2", text="second"))
    stack = QUndoStack()
    editor = MarkdownEditorWidget()
    qtbot.addWidget(editor)
    editor.set_card(document, stack, "c_1")

    document.remove_card("c_1")
    editor.set_card(document, stack, "c_2")  # must not raise

    assert editor.tags_edit.text() == ""
    assert editor.text_edit.toPlainText() == "second"
