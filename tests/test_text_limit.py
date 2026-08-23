from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QPlainTextEdit

from indexcards.utils.text_limit import enforce_char_limit


def _type(editor: QPlainTextEdit, text: str) -> None:
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertText(text)


def _editor() -> QPlainTextEdit:
    # A bare QTextDocument() with no widget/layout attached never fires
    # contentsChange at all — the limiter needs a real document owner
    # (any QGraphicsTextItem/QPlainTextEdit) to observe edits against.
    return QPlainTextEdit()


def test_typing_within_limit_is_unaffected(qtbot):
    editor = _editor()
    qtbot.addWidget(editor)
    enforce_char_limit(editor.document(), 10)

    _type(editor, "short")

    assert editor.toPlainText() == "short"


def test_typing_past_limit_is_trimmed_to_fit(qtbot):
    editor = _editor()
    qtbot.addWidget(editor)
    enforce_char_limit(editor.document(), 10)

    _type(editor, "way too much text")

    assert editor.toPlainText() == "way too mu"


def test_typing_further_once_at_limit_is_blocked(qtbot):
    editor = _editor()
    qtbot.addWidget(editor)
    enforce_char_limit(editor.document(), 10)
    _type(editor, "0123456789")

    _type(editor, "extra")

    assert editor.toPlainText() == "0123456789"


def test_pasting_a_large_block_is_trimmed_not_rejected(qtbot):
    editor = _editor()
    qtbot.addWidget(editor)
    enforce_char_limit(editor.document(), 10)

    cursor = editor.textCursor()
    cursor.insertText("x" * 500)  # simulates a large paste in one operation

    assert editor.toPlainText() == "x" * 10


def test_inserting_in_the_middle_with_room_trims_only_the_overflow(qtbot):
    editor = _editor()
    qtbot.addWidget(editor)
    enforce_char_limit(editor.document(), 10)
    _type(editor, "01234")  # 5 chars — 5 of room left

    cursor = editor.textCursor()
    cursor.setPosition(2)
    cursor.insertText("ABCDEFGH")  # 8 chars inserted, only 5 fit

    assert editor.toPlainText() == "01ABCDE234"


def test_inserting_in_the_middle_already_at_limit_is_fully_rejected(qtbot):
    editor = _editor()
    qtbot.addWidget(editor)
    enforce_char_limit(editor.document(), 10)
    _type(editor, "0123456789")  # already at the limit, no room at all

    cursor = editor.textCursor()
    cursor.setPosition(2)
    cursor.insertText("ab")

    assert editor.toPlainText() == "0123456789"


def test_deleting_below_limit_is_unaffected(qtbot):
    editor = _editor()
    qtbot.addWidget(editor)
    enforce_char_limit(editor.document(), 10)
    _type(editor, "0123456789")

    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.deletePreviousChar()

    assert editor.toPlainText() == "012345678"
