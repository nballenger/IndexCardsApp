from __future__ import annotations

from PySide6.QtWidgets import QAbstractItemView, QTableView, QVBoxLayout, QWidget

from indexcards.list_view.card_table_model import COLUMN_COLOR, COLUMN_TAGS
from indexcards.list_view.color_delegate import ColorDelegate
from indexcards.list_view.tag_delegate import TagDelegate


class ListViewWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.table_view = QTableView(self)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.setItemDelegateForColumn(COLUMN_COLOR, ColorDelegate(self.table_view))
        self.table_view.setItemDelegateForColumn(COLUMN_TAGS, TagDelegate(self.table_view))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.table_view)

    def set_model(self, model) -> None:
        self.table_view.setModel(model)
