from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QHeaderView, QWidget


class SortableColumnsHeaderView(QHeaderView):
    """A horizontal header where only the given columns can be clicked to
    sort. Clicks on any other column (e.g. Links, which has no meaningful
    sort order) are swallowed before QHeaderView's own click-to-sort
    handling runs, so they neither show a sort indicator nor reorder rows.
    """

    def __init__(self, sortable_columns: frozenset[int], parent: QWidget | None = None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self._sortable_columns = sortable_columns

    def _is_sortable_click(self, event: QMouseEvent) -> bool:
        return self.logicalIndexAt(event.position().toPoint()) in self._sortable_columns

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self._is_sortable_click(event):
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if not self._is_sortable_click(event):
            return
        super().mouseReleaseEvent(event)
