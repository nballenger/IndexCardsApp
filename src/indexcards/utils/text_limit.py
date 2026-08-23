from __future__ import annotations

from collections.abc import Callable

from PySide6.QtGui import QTextCursor, QTextDocument


def enforce_char_limit(document: QTextDocument, max_length: int) -> Callable[[int, int, int], None]:
    """Keeps document from ever holding more than max_length plain-text
    characters, live as the user types or pastes — trims back whatever
    was just inserted rather than blocking the keystroke outright, so a
    paste that overflows the limit still lands, just cut to fit.

    QTextDocument/QPlainTextEdit have no built-in max-length (unlike
    QLineEdit.setMaxLength()), so this is the standard way to add one:
    react to contentsChange and remove the excess. The removeSelectedText()
    call below re-enters this handler with chars_added == 0 (a pure
    deletion), which the guard at the top already no-ops on — no need to
    block signals to avoid recursing.

    Returns the connected slot, so a caller that wants this to apply only
    for the duration of an interactive edit session (rather than for the
    document's whole lifetime — which would also clip a longer-than-limit
    value the moment it's merely loaded/displayed, not just when someone
    actually types past the limit) can later disconnect it:
    document.contentsChange.disconnect(returned_slot).
    """

    def _on_contents_change(position: int, _chars_removed: int, chars_added: int) -> None:
        if chars_added == 0:
            return
        overflow = len(document.toPlainText()) - max_length
        if overflow <= 0:
            return
        end = position + chars_added
        start = max(position, end - overflow)
        cursor = QTextCursor(document)
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()

    document.contentsChange.connect(_on_contents_change)
    return _on_contents_change
