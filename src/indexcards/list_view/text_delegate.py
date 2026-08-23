from __future__ import annotations

from PySide6.QtCore import QEvent, QModelIndex, Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QPlainTextEdit, QStyledItemDelegate, QWidget

from indexcards.models.card import MAX_TEXT_LENGTH
from indexcards.utils.text_limit import enforce_char_limit


class TextDelegate(QStyledItemDelegate):
    """Multi-line editor for the Text column.

    Qt's default QAbstractItemDelegate leaves Enter/Return alone for a
    QTextEdit/QPlainTextEdit editor (so it inserts a newline rather than
    committing) — this overrides that so Enter keeps meaning "commit",
    consistent with every other column and with list-view row navigation;
    Shift+Enter inserts a newline instead.
    """

    def createEditor(self, parent: QWidget, option, index: QModelIndex) -> QWidget:
        editor = QPlainTextEdit(parent)
        editor.setMinimumHeight(60)
        return editor

    def setEditorData(self, editor: QPlainTextEdit, index: QModelIndex) -> None:
        text = index.model().data(index, Qt.ItemDataRole.EditRole) or ""
        editor.setPlainText(text)
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        editor.setTextCursor(cursor)
        # Connected after the initial (possibly already-over-the-limit,
        # e.g. from a file saved before this limit existed) value is
        # loaded, so it only reacts to further typing/pasting, not to
        # setPlainText() above.
        enforce_char_limit(editor.document(), MAX_TEXT_LENGTH)

    def setModelData(self, editor: QPlainTextEdit, model, index: QModelIndex) -> None:
        model.setData(index, editor.toPlainText(), Qt.ItemDataRole.EditRole)

    def eventFilter(self, editor: QWidget, event: QEvent) -> bool:
        if event.type() == QEvent.Type.KeyPress and event.key() in (
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
        ):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                return False  # let the editor insert a newline
            self.commitData.emit(editor)
            self.closeEditor.emit(editor)
            return True
        return super().eventFilter(editor, event)
