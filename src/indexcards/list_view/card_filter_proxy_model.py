from __future__ import annotations

from PySide6.QtCore import QModelIndex, QSortFilterProxyModel

from indexcards.search import matches


class CardFilterProxyModel(QSortFilterProxyModel):
    """Filters list rows to cards whose text or tags match the search query."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._query = ""

    def set_query(self, query: str) -> None:
        self._query = query
        # invalidateFilter()/invalidateRowsFilter() are both deprecated in
        # this Qt6 version; plain invalidate() is the current replacement.
        self.invalidate()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model = self.sourceModel()
        if model is None:
            return True
        card = model.card_at_row(source_row)
        if card is None:
            return False  # transiently stale row (see CardTableModel.card_at_row)
        return matches(card, self._query)
