from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from indexcards.models.document import Document

COLUMN_TEXT = 0
COLUMN_COLOR = 1
COLUMN_TAGS = 2
_HEADERS = ["Text", "Color", "Tags"]
_ROOT_INDEX = QModelIndex()


class CardTableModel(QAbstractTableModel):
    """Read/write view of a Document's cards, kept in sync via its signals."""

    def __init__(self, document: Document, parent=None) -> None:
        super().__init__(parent)
        self._document = document
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

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role not in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return None
        card = self._document.get_card(self._card_ids[index.row()])
        column = index.column()
        if column == COLUMN_TEXT:
            return card.text
        if column == COLUMN_COLOR:
            return card.color
        if column == COLUMN_TAGS:
            return ", ".join(card.tags)
        return None

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
