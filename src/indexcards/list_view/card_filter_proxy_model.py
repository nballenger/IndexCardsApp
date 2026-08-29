from __future__ import annotations

from PySide6.QtCore import QModelIndex, QSortFilterProxyModel, Qt

from indexcards.list_view.card_table_model import COLUMN_COLOR
from indexcards.models.document import Document
from indexcards.search import matches


class CardFilterProxyModel(QSortFilterProxyModel):
    """Filters list rows to cards matching the search query (see
    indexcards.search.matches for exactly what's matched)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._query = ""
        self._active_stack_id: str | None = None

    @property
    def document(self) -> Document:
        """The active Document, reached through the source model — lets
        ColorDelegate resolve a card's color slot against the active
        theme without needing its own reference to the document (the
        delegate only ever sees a QModelIndex against this proxy)."""
        return self.sourceModel().document

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

    def _color_sort_order(self) -> dict[str, int]:
        """Maps each slot id to its sort position: non-orphaned slots in
        the active theme's own order, then orphaned slots after (in their
        own existing relative order) — the same "theme order, then
        orphans" rule used for arrange-by-color and the color key."""
        slots = self.document.theme.slots
        ordered_ids = [slot.id for slot in slots if not slot.orphaned]
        ordered_ids += [slot.id for slot in slots if slot.orphaned]
        return {slot_id: position for position, slot_id in enumerate(ordered_ids)}

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        if left.column() == COLUMN_COLOR and right.column() == COLUMN_COLOR:
            order = self._color_sort_order()
            left_slot_id = self.sourceModel().data(left, Qt.ItemDataRole.EditRole) or ""
            right_slot_id = self.sourceModel().data(right, Qt.ItemDataRole.EditRole) or ""
            return order.get(left_slot_id, 0) < order.get(right_slot_id, 0)
        return super().lessThan(left, right)
