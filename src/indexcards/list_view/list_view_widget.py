from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QMenu,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from indexcards.list_view.card_table_model import COLUMN_COLOR, COLUMN_TAGS
from indexcards.list_view.color_delegate import ColorDelegate
from indexcards.list_view.tag_delegate import TagDelegate
from indexcards.widgets.dialogs import confirm_delete_cards


class ListViewWidget(QWidget):
    currentCardChanged = Signal(object)  # str card_id, or None

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.table_view = QTableView(self)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.setItemDelegateForColumn(COLUMN_COLOR, ColorDelegate(self.table_view))
        self.table_view.setItemDelegateForColumn(COLUMN_TAGS, TagDelegate(self.table_view))
        self.table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self._show_context_menu)

        self.add_button = QPushButton("Add Card", self)
        self.delete_button = QPushButton("Delete Card", self)
        self.add_button.clicked.connect(self._add_card)
        self.delete_button.clicked.connect(self._delete_selected_cards)

        toolbar_layout = QHBoxLayout()
        toolbar_layout.addWidget(self.add_button)
        toolbar_layout.addWidget(self.delete_button)
        toolbar_layout.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(toolbar_layout)
        layout.addWidget(self.table_view)

        delete_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Backspace), self.table_view)
        delete_shortcut.activated.connect(self._delete_selected_cards)

    def set_model(self, model) -> None:
        self.table_view.setModel(model)
        selection_model = self.table_view.selectionModel()
        if selection_model is not None:
            selection_model.currentRowChanged.connect(self._on_current_row_changed)

    def _on_current_row_changed(self, current, previous) -> None:
        model = self.table_view.model()
        if model is None or not current.isValid():
            self.currentCardChanged.emit(None)
            return
        self.currentCardChanged.emit(model.card_id_at_row(current.row()))

    def _selected_rows(self) -> list[int]:
        selection_model = self.table_view.selectionModel()
        if selection_model is None:
            return []
        return [index.row() for index in selection_model.selectedRows()]

    def _add_card(self) -> None:
        model = self.table_view.model()
        if model is not None:
            model.add_card()

    def _delete_selected_cards(self) -> None:
        model = self.table_view.model()
        if model is None:
            return
        rows = self._selected_rows()
        if not rows:
            return
        card_ids = [model.card_id_at_row(row) for row in rows]
        incident_link_count = model.incident_link_count_for_card_ids(card_ids)
        if not confirm_delete_cards(self, len(card_ids), incident_link_count):
            return
        model.remove_cards_at_rows(rows)

    def _show_context_menu(self, position) -> None:
        model = self.table_view.model()
        if model is None:
            return
        index = self.table_view.indexAt(position)
        if index.isValid() and not self.table_view.selectionModel().isRowSelected(
            index.row(), index.parent()
        ):
            self.table_view.selectionModel().select(
                index,
                Qt.ItemSelectionFlag.ClearAndSelect | Qt.ItemSelectionFlag.Rows,
            )

        menu = QMenu(self.table_view)
        add_action = menu.addAction("Add Card")
        add_action.triggered.connect(self._add_card)
        if self._selected_rows():
            delete_action = menu.addAction("Delete Card")
            delete_action.triggered.connect(self._delete_selected_cards)
        menu.exec(self.table_view.viewport().mapToGlobal(position))
