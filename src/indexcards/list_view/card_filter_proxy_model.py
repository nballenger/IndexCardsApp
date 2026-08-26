from __future__ import annotations

from PySide6.QtCore import QModelIndex, QSortFilterProxyModel, Qt

from indexcards.list_view.card_table_model import COLUMN_COLOR
from indexcards.models.palette import PALETTE
from indexcards.search import matches

# Sorting the Color column by its display string (a hex code) wouldn't
# match the order cards can actually be assigned a color in (the palette
# dropdown/menu) — this maps each hex value to its position there instead.
_COLOR_SORT_ORDER = {
    hex_value.lower(): position for position, hex_value in enumerate(PALETTE.values())
}


class CardFilterProxyModel(QSortFilterProxyModel):
    """Filters list rows to cards matching the search query (see
    indexcards.search.matches for exactly what's matched)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._query = ""
        self._active_stack_id: str | None = None

    def set_query(self, query: str) -> None:
        self._query = query
        # invalidateFilter()/invalidateRowsFilter() are both deprecated in
        # this Qt6 version; plain invalidate() is the current replacement.
        self.invalidate()

    def set_active_stack_id(self, stack_id: str | None) -> None:
        """Restricts visible rows to cards in this stack — or, with
        stack_id=None, to cards not in any stack at all ("On Canvas")."""
        if stack_id == self._active_stack_id:
            return
        self._active_stack_id = stack_id
        self.invalidate()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model = self.sourceModel()
        if model is None:
            return True
        card = model.card_at_row(source_row)
        if card is None:
            return False  # transiently stale row (see CardTableModel.card_at_row)
        if card.stack_id != self._active_stack_id:
            return False
        return matches(card, self._query)

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        if left.column() == COLUMN_COLOR and right.column() == COLUMN_COLOR:
            left_hex = self.sourceModel().data(left, Qt.ItemDataRole.EditRole) or ""
            right_hex = self.sourceModel().data(right, Qt.ItemDataRole.EditRole) or ""
            return _COLOR_SORT_ORDER.get(left_hex.lower(), 0) < _COLOR_SORT_ORDER.get(
                right_hex.lower(), 0
            )
        return super().lessThan(left, right)
