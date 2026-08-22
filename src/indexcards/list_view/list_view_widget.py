from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from indexcards.list_view.card_filter_proxy_model import CardFilterProxyModel
from indexcards.list_view.card_table_model import (
    COLUMN_COLOR,
    COLUMN_TAGS,
    COLUMN_TEXT,
    CardTableModel,
)
from indexcards.list_view.color_delegate import ColorDelegate
from indexcards.list_view.tag_delegate import TagDelegate
from indexcards.list_view.text_delegate import TextDelegate
from indexcards.widgets.dialogs import confirm_delete_cards

_EMPTY_STATE_TEXT = 'No cards yet — click "Add Card" to create one.'


class ListViewWidget(QWidget):
    currentCardChanged = Signal(object)  # str card_id, or None
    cardCreated = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.model: CardTableModel | None = None
        self.proxy_model = CardFilterProxyModel(self)

        self.table_view = QTableView(self)
        self.table_view.setModel(self.proxy_model)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.setItemDelegateForColumn(COLUMN_TEXT, TextDelegate(self.table_view))
        self.table_view.setItemDelegateForColumn(COLUMN_COLOR, ColorDelegate(self.table_view))
        self.table_view.setItemDelegateForColumn(COLUMN_TAGS, TagDelegate(self.table_view))
        self.table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self._show_context_menu)
        self.table_view.clicked.connect(self._on_cell_clicked)

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
        self.table_view.installEventFilter(self)

        self.empty_label = QLabel(_EMPTY_STATE_TEXT, self.table_view.viewport())
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: gray;")
        self.empty_label.setWordWrap(True)
        self.proxy_model.rowsInserted.connect(self._update_empty_state)
        self.proxy_model.rowsRemoved.connect(self._update_empty_state)
        self.proxy_model.modelReset.connect(self._update_empty_state)
        self.proxy_model.layoutChanged.connect(self._update_empty_state)
        self._update_empty_state()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.empty_label.setGeometry(self.table_view.viewport().rect())

    def eventFilter(self, watched, event) -> bool:
        if (
            watched is self.table_view
            and event.type() == QEvent.Type.KeyPress
            and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and self._handle_enter_on_last_row()
        ):
            return True
        return super().eventFilter(watched, event)

    def _handle_enter_on_last_row(self) -> bool:
        if self.model is None:
            return False
        if self.table_view.state() == QAbstractItemView.State.EditingState:
            return False  # let Enter commit the in-progress cell edit as usual
        current = self.table_view.currentIndex()
        if not current.isValid() or current.row() != self.proxy_model.rowCount() - 1:
            return False
        card_id = self.model.add_card()
        # Enter-on-last-row is a spreadsheet-style flow — keep the user
        # typing inline in the new row's Text cell rather than jumping
        # them elsewhere.
        if card_id is not None:
            self.edit_text_cell(card_id)
        return True

    def edit_text_cell(self, card_id: str) -> None:
        row = self.model.row_for_card_id(card_id)
        if row is None:
            return
        proxy_index = self.proxy_model.mapFromSource(self.model.index(row, COLUMN_TEXT))
        if not proxy_index.isValid():
            return
        self.table_view.setCurrentIndex(proxy_index)
        self.table_view.edit(proxy_index)

    def _on_cell_clicked(self, index) -> None:
        if index.column() == COLUMN_COLOR:
            self.table_view.edit(index)

    def _update_empty_state(self, *_args) -> None:
        self.empty_label.setGeometry(self.table_view.viewport().rect())
        self.empty_label.setVisible(self.proxy_model.rowCount() == 0)

    def set_model(self, model: CardTableModel) -> None:
        self.model = model
        self.proxy_model.setSourceModel(model)
        selection_model = self.table_view.selectionModel()
        if selection_model is not None:
            selection_model.currentRowChanged.connect(self._on_current_row_changed)
        self._update_empty_state()

    def set_search_query(self, query: str) -> None:
        self.proxy_model.set_query(query)

    def _on_current_row_changed(self, current, previous) -> None:
        if self.model is None or not current.isValid():
            self.currentCardChanged.emit(None)
            return
        source_row = self.proxy_model.mapToSource(current).row()
        self.currentCardChanged.emit(self.model.card_id_at_row(source_row))

    def _selected_rows(self) -> list[int]:
        selection_model = self.table_view.selectionModel()
        if selection_model is None:
            return []
        return [
            self.proxy_model.mapToSource(index).row() for index in selection_model.selectedRows()
        ]

    def _add_card(self) -> None:
        if self.model is None:
            return
        card_id = self.model.add_card()
        if card_id is not None:
            self.cardCreated.emit(card_id)

    def _delete_selected_cards(self) -> None:
        if self.model is None:
            return
        rows = self._selected_rows()
        if not rows:
            return
        card_ids = [self.model.card_id_at_row(row) for row in rows]
        incident_link_count = self.model.incident_link_count_for_card_ids(card_ids)
        if not confirm_delete_cards(self, len(card_ids), incident_link_count):
            return
        self.model.remove_cards_at_rows(rows)

    def _show_context_menu(self, position) -> None:
        if self.model is None:
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
