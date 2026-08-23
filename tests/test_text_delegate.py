from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit

from indexcards.list_view.card_table_model import COLUMN_TEXT, CardTableModel
from indexcards.list_view.text_delegate import TextDelegate
from indexcards.models.card import MAX_TEXT_LENGTH, Card
from indexcards.models.document import Document


def _key_event(key, modifiers=Qt.KeyboardModifier.NoModifier) -> QKeyEvent:
    return QKeyEvent(QEvent.Type.KeyPress, key, modifiers)


def test_create_editor_is_multiline():
    delegate = TextDelegate()
    editor = delegate.createEditor(None, None, None)
    assert isinstance(editor, QPlainTextEdit)


def test_plain_enter_commits_and_closes(qtbot):
    delegate = TextDelegate()
    editor = QPlainTextEdit()
    qtbot.addWidget(editor)
    committed = []
    closed = []
    delegate.commitData.connect(committed.append)
    delegate.closeEditor.connect(lambda ed, *_hint: closed.append(ed))

    handled = delegate.eventFilter(editor, _key_event(Qt.Key.Key_Return))

    assert handled is True
    assert committed == [editor]
    assert closed == [editor]


def test_shift_enter_does_not_commit():
    delegate = TextDelegate()
    editor = QPlainTextEdit()
    committed = []
    delegate.commitData.connect(committed.append)

    handled = delegate.eventFilter(
        editor, _key_event(Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    )

    assert handled is False  # left unhandled so the editor inserts a newline
    assert committed == []


def test_other_keys_are_not_intercepted():
    delegate = TextDelegate()
    editor = QPlainTextEdit()

    handled = delegate.eventFilter(editor, _key_event(Qt.Key.Key_A))

    assert handled is False


def test_typing_past_char_limit_in_editor_is_blocked(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="hi"))
    model = CardTableModel(document)
    index = model.index(0, COLUMN_TEXT)
    delegate = TextDelegate()
    editor = delegate.createEditor(None, None, index)
    qtbot.addWidget(editor)
    delegate.setEditorData(editor, index)

    cursor = editor.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    cursor.insertText("a" * (MAX_TEXT_LENGTH + 40))

    assert len(editor.toPlainText()) == MAX_TEXT_LENGTH


def test_loading_already_over_limit_value_is_not_clipped(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="a" * (MAX_TEXT_LENGTH + 40)))
    model = CardTableModel(document)
    index = model.index(0, COLUMN_TEXT)
    delegate = TextDelegate()
    editor = delegate.createEditor(None, None, index)
    qtbot.addWidget(editor)

    delegate.setEditorData(editor, index)

    assert len(editor.toPlainText()) == MAX_TEXT_LENGTH + 40
