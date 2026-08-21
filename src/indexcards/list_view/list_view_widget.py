from __future__ import annotations

from PySide6.QtWidgets import QAbstractItemView, QTableView, QVBoxLayout, QWidget


class ListViewWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.table_view = QTableView(self)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.verticalHeader().setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.table_view)

    def set_model(self, model) -> None:
        self.table_view.setModel(model)
