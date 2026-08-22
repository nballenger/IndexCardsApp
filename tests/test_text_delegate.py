from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QPlainTextEdit

from indexcards.list_view.text_delegate import TextDelegate


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
