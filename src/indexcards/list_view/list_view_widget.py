from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QKeySequence, QMouseEvent, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QMenu,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from indexcards.feature_flags import TAGS_ENABLED
from indexcards.list_view.card_filter_proxy_model import CardFilterProxyModel
from indexcards.list_view.card_table_model import (
    COLUMN_COLOR,
    COLUMN_TAGS,
    COLUMN_TEXT,
    CardTableModel,
)
from indexcards.list_view.color_delegate import ColorDelegate
from indexcards.list_view.sortable_header_view import SortableColumnsHeaderView
from indexcards.list_view.tag_delegate import TagDelegate
from indexcards.list_view.text_delegate import TextDelegate
from indexcards.widgets.dialogs import confirm_delete_cards

_EMPTY_DOCUMENT_TEXT = "No cards yet — double-click here to create one."
_EMPTY_SEARCH_TEXT = "No cards match the current search."

_MIN_COLUMN_WIDTH = 60
_COLOR_COLUMN_FRACTION = 0.10
_TEXT_COLUMN_FRACTION = 0.70
# Below this, the viewport almost certainly hasn't been through a real
# layout pass yet (e.g. set_model() called during MainWindow.__init__,
# before the window is ever shown) — applying fractions against it and
# locking that in would leave columns stuck at bogus, too-small widths.
_MIN_BELIEVABLE_VIEWPORT_WIDTH = 200
# Links isn't in either fraction — it's the last section, which
# setStretchLastSection makes fill whatever width is left (~20% at the
# fractions above), and Qt doesn't allow interactively resizing a
# stretched last section, so SortableColumnsHeaderView blocking its
# header clicks below doesn't cost it any resize ability it otherwise had.


class ListViewWidget(QWidget):
    currentCardChanged = Signal(object)  # str card_id, or None
    cardCreated = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.model: CardTableModel | None = None
        self.proxy_model = CardFilterProxyModel(self)
        self._columns_sized = False
        self._header_configured = False

        self.table_view = QTableView(self)
        header = SortableColumnsHeaderView(frozenset({COLUMN_TEXT, COLUMN_COLOR}), self.table_view)
        self.table_view.setHorizontalHeader(header)
        self.table_view.setModel(self.proxy_model)
        header.setStretchLastSection(True)
        header.setMinimumSectionSize(_MIN_COLUMN_WIDTH)
        header.setSectionsClickable(True)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.setItemDelegateForColumn(COLUMN_TEXT, TextDelegate(self.table_view))
        self.table_view.setItemDelegateForColumn(COLUMN_COLOR, ColorDelegate(self.table_view))
        self.table_view.setItemDelegateForColumn(COLUMN_TAGS, TagDelegate(self.table_view))
        self.table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self._show_context_menu)
        self.table_view.clicked.connect(self._on_cell_clicked)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.table_view)

        delete_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Backspace), self.table_view)
        delete_shortcut.activated.connect(self._delete_selected_cards)
        self.table_view.installEventFilter(self)
        self.table_view.viewport().installEventFilter(self)

        self.empty_label = QLabel(_EMPTY_DOCUMENT_TEXT, self.table_view.viewport())
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: gray;")
        self.empty_label.setWordWrap(True)
        # Otherwise this label (which covers the whole viewport whenever no
        # rows are visible) would swallow the double-click meant to create
        # a card, since it sits on top of the viewport in painting order.
        self.empty_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.proxy_model.rowsInserted.connect(self._update_empty_state)
        self.proxy_model.rowsRemoved.connect(self._update_empty_state)
        self.proxy_model.modelReset.connect(self._update_empty_state)
        self.proxy_model.layoutChanged.connect(self._update_empty_state)
        self._update_empty_state()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.empty_label.setGeometry(self.table_view.viewport().rect())

    def _apply_initial_column_widths(self) -> None:
        if self.model is None:
            return  # no real columns to size yet — wait for set_model()
        width = self.table_view.viewport().width()
        if width < _MIN_BELIEVABLE_VIEWPORT_WIDTH:
            return  # not really laid out yet — a later resize will retry
        self.table_view.setColumnWidth(
            COLUMN_COLOR, max(_MIN_COLUMN_WIDTH, int(width * _COLOR_COLUMN_FRACTION))
        )
        self.table_view.setColumnWidth(
            COLUMN_TEXT, max(_MIN_COLUMN_WIDTH, int(width * _TEXT_COLUMN_FRACTION))
        )
        self._columns_sized = True

    def eventFilter(self, watched, event) -> bool:
        if (
            watched is self.table_view
            and event.type() == QEvent.Type.KeyPress
            and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and self._handle_enter_on_last_row()
        ):
            return True
        if watched is self.table_view.viewport():
            if event.type() == QEvent.Type.Resize and not self._columns_sized:
                self._apply_initial_column_widths()
            elif event.type() == QEvent.Type.MouseButtonDblClick and (
                self._handle_background_double_click(event)
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

    def _handle_background_double_click(self, event: QMouseEvent) -> bool:
        if self.model is None:
            return False
        if self.table_view.indexAt(event.position().toPoint()).isValid():
            return False  # let the normal double-click-to-edit-cell behavior proceed
        card_id = self.model.add_card()
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
        visible_count = self.proxy_model.rowCount()
        if visible_count > 0:
            self.empty_label.setVisible(False)
            return
        total_count = self.model.rowCount() if self.model is not None else 0
        self.empty_label.setText(_EMPTY_DOCUMENT_TEXT if total_count == 0 else _EMPTY_SEARCH_TEXT)
        self.empty_label.setVisible(True)

    def set_model(self, model: CardTableModel) -> None:
        if self.model is not None:
            self.model.rowsInserted.disconnect(self._update_empty_state)
            self.model.rowsRemoved.disconnect(self._update_empty_state)
            self.model.modelReset.disconnect(self._update_empty_state)
        self.model = model
        # Listened to directly (not just via the proxy's own re-emitted
        # signals below) because if a search is already filtering every
        # row out, the proxy's visible row count stays at 0 across a
        # source-side add/remove — no proxy signal fires — so relying on
        # the proxy alone would leave this label showing stale text.
        model.rowsInserted.connect(self._update_empty_state)
        model.rowsRemoved.connect(self._update_empty_state)
        model.modelReset.connect(self._update_empty_state)
        self.proxy_model.setSourceModel(model)
        if not TAGS_ENABLED:
            self.table_view.setColumnHidden(COLUMN_TAGS, True)
        if not self._header_configured:
            # Needs a real (non-empty-column) model already attached to the
            # header to take effect — doing this in __init__ against the
            # not-yet-sourced proxy model is silently a no-op.
            header = self.table_view.horizontalHeader()
            self.table_view.setSortingEnabled(True)
            header.setSortIndicator(-1, Qt.SortOrder.AscendingOrder)  # start unsorted
            header.moveSection(1, 0)  # visual order becomes Color, Text, Tags, Links
            self._header_configured = True
        if not self._columns_sized:
            # The viewport may already have been resized before a model was
            # attached (that resize's own attempt would have no-op'd), so
            # try again now that there are real columns to size.
            self._apply_initial_column_widths()
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
