from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QUndoStack

from indexcards.commands.card_commands import (
    ChangeColorCommand,
    ChangeTagsCommand,
    EditCardTextCommand,
)
from indexcards.models.document import Document

COLUMN_TEXT = 0
COLUMN_COLOR = 1
COLUMN_TAGS = 2
_HEADERS = ["Text", "Color", "Tags"]
_ROOT_INDEX = QModelIndex()


class CardTableModel(QAbstractTableModel):
    """Read/write view of a Document's cards, kept in sync via its signals.

    Edits are only accepted when constructed with an undo_stack: setData()
    pushes an undo command rather than mutating the Document directly, so
    list-view edits and canvas edits (future milestones) share one history.
    """

    def __init__(
        self, document: Document, undo_stack: QUndoStack | None = None, parent=None
    ) -> None:
        super().__init__(parent)
        self._document = document
        self._undo_stack = undo_stack
        self._card_ids: list[str] = list(document.cards.keys())
        document.cardAdded.connect(self._on_card_added)
        document.cardRemoved.connect(self._on_card_removed)
        document.cardChanged.connect(self._on_card_changed)

    def card_id_at_row(self, row: int) -> str:
        return self._card_ids[row]

    # -- QAbstractTableModel interface --------------------------------------

    def rowCount(self, parent: QModelIndex = _ROOT_INDEX) -> int:
        if parent.isValid():
            return 0
        return len(self._card_ids)

    def columnCount(self, parent: QModelIndex = _ROOT_INDEX) -> int:
        if parent.isValid():
            return 0
        return len(_HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole or orientation != Qt.Orientation.Horizontal:
            return None
        return _HEADERS[section]

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if not index.isValid() or self._undo_stack is None:
            return base
        return base | Qt.ItemFlag.ItemIsEditable

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        card = self._document.get_card(self._card_ids[index.row()])
        column = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if column == COLUMN_TEXT:
                return card.text
            if column == COLUMN_COLOR:
                return card.color
            if column == COLUMN_TAGS:
                return ", ".join(card.tags)
        elif role == Qt.ItemDataRole.EditRole:
            if column == COLUMN_TEXT:
                return card.text
            if column == COLUMN_COLOR:
                return card.color
            if column == COLUMN_TAGS:
                return list(card.tags)
        return None

    def setData(self, index: QModelIndex, value, role=Qt.ItemDataRole.EditRole) -> bool:
        if role != Qt.ItemDataRole.EditRole or self._undo_stack is None or not index.isValid():
            return False

        card_id = self._card_ids[index.row()]
        card = self._document.get_card(card_id)
        column = index.column()

        if column == COLUMN_TEXT:
            if value == card.text:
                return False
            self._undo_stack.push(EditCardTextCommand(self._document, card_id, card.text, value))
            return True
        if column == COLUMN_COLOR:
            if value == card.color:
                return False
            self._undo_stack.push(
                ChangeColorCommand(self._document, card_id, card.color, value)
            )
            return True
        if column == COLUMN_TAGS:
            new_tags = list(value)
            if new_tags == card.tags:
                return False
            self._undo_stack.push(
                ChangeTagsCommand(self._document, card_id, card.tags, new_tags)
            )
            return True
        return False

    # -- Document signal handlers --------------------------------------------

    def _on_card_added(self, card_id: str) -> None:
        row = len(self._card_ids)
        self.beginInsertRows(QModelIndex(), row, row)
        self._card_ids.append(card_id)
        self.endInsertRows()

    def _on_card_removed(self, card_id: str) -> None:
        if card_id not in self._card_ids:
            return
        row = self._card_ids.index(card_id)
        self.beginRemoveRows(QModelIndex(), row, row)
        del self._card_ids[row]
        self.endRemoveRows()

    def _on_card_changed(self, card_id: str, fields: frozenset[str]) -> None:
        if card_id not in self._card_ids:
            return
        row = self._card_ids.index(card_id)
        top_left = self.index(row, 0)
        bottom_right = self.index(row, self.columnCount() - 1)
        self.dataChanged.emit(top_left, bottom_right)
