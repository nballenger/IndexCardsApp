from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QModelIndex, Qt
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QCloseEvent,
    QColor,
    QKeySequence,
    QShortcut,
    QUndoGroup,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QDialog,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QToolBar,
)

from indexcards.app_settings import AppSettings
from indexcards.arrange.auto_arrange import arrange_avoiding_pinned
from indexcards.canvas.canvas_scene import CanvasScene
from indexcards.canvas.canvas_view import VIEW_EXTENTS_MARGIN, CanvasView
from indexcards.commands.arrange_commands import AutoArrangeCommand
from indexcards.commands.card_commands import DeleteCardCommand, TogglePinCommand
from indexcards.commands.document_commands import ChangeCanvasBackgroundCommand
from indexcards.commands.link_commands import AddLinkCommand, DeleteLinkCommand
from indexcards.list_view.card_table_model import CardTableModel
from indexcards.list_view.list_view_widget import ListViewWidget
from indexcards.models.document import Document
from indexcards.models.link import Link
from indexcards.persistence.file_io import load_document, save_document
from indexcards.utils.ids import new_link_id
from indexcards.widgets.dialogs import confirm_delete_cards
from indexcards.widgets.search_bar import SearchBar
from indexcards.widgets.settings_dialog import SettingsDialog

if TYPE_CHECKING:
    from indexcards.window_manager import WindowManager

FILE_DIALOG_FILTER = "Index Cards Files (*.idxcards);;All Files (*)"


class MainWindow(QMainWindow):
    """One window per open file."""

    def __init__(self, window_manager: WindowManager | None = None) -> None:
        super().__init__()
        self._window_manager = window_manager
        self._undo_group = (
            window_manager.undo_group if window_manager is not None else QUndoGroup(self)
        )
        self._settings = window_manager.settings if window_manager is not None else AppSettings()

        self.document: Document | None = None
        self.card_table_model: CardTableModel | None = None
        self.canvas_scene: CanvasScene | None = None
        self.undo_stack: QUndoStack | None = None
        self._current_path: Path | None = None
        self._syncing_selection = False
        self._current_search_query = ""
        self._links_visible = True

        self.setWindowTitle("Index Cards")
        self.resize(1000, 700)

        self.canvas_view = CanvasView(self)
        self.list_view = ListViewWidget(self, settings=self._settings)
        self.tabs = QTabWidget(self)
        self.tabs.addTab(self.canvas_view, "Canvas")
        self.tabs.addTab(self.list_view, "List")
        self.setCentralWidget(self.tabs)

        self.list_view.currentCardChanged.connect(self._on_list_current_card_changed)
        self.list_view.cardCreated.connect(self._select_and_focus_new_card)
        self.canvas_view.link_controller.linkRequested.connect(self._on_link_requested)
        self.canvas_view.deleteRequested.connect(self._on_canvas_delete_requested)
        self.canvas_view.cardCreated.connect(self._select_and_focus_new_card)
        self.canvas_view.backgroundChangeRequested.connect(self._on_change_canvas_background)

        # Link Mode is entered by holding Option (Qt's AltModifier — the
        # physical key Qt calls "Alt" is labelled "Option" on Mac
        # keyboards) rather than a toggle button, so it has to be tracked
        # at the application level: a plain keyPressEvent override on
        # canvas_view would miss the key whenever some other widget (the
        # search bar, a card being text-edited) has focus instead.
        QApplication.instance().installEventFilter(self)

        self.search_bar = SearchBar(self)
        self.search_bar.queryChanged.connect(self._on_search_query_changed)
        self.search_toolbar = QToolBar("Search", self)
        self.search_toolbar.addWidget(self.search_bar)
        self.addToolBar(self.search_toolbar)

        find_shortcut = QShortcut(QKeySequence.StandardKey.Find, self)
        find_shortcut.activated.connect(self._focus_search_bar)

        new_card_shortcut = QShortcut(QKeySequence("Ctrl+Shift+N"), self)
        new_card_shortcut.activated.connect(self._on_create_card_shortcut)

        self._build_menu()
        self._set_document(
            Document(
                name="Untitled", canvas_background_color=self._settings.default_background_color
            ),
            path=None,
        )

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")

        self.settings_action = QAction("Settings...", self)
        self.settings_action.setShortcut(QKeySequence.StandardKey.Preferences)
        self.settings_action.setMenuRole(QAction.MenuRole.PreferencesRole)
        self.settings_action.triggered.connect(self._on_open_settings)
        file_menu.addAction(self.settings_action)
        file_menu.addSeparator()

        new_action = QAction("&New Window", self)
        new_action.setShortcut(QKeySequence.StandardKey.New)
        new_action.triggered.connect(self._on_new)
        file_menu.addAction(new_action)

        open_action = QAction("&Open...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self._on_open)
        file_menu.addAction(open_action)

        save_action = QAction("&Save", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self._on_save)
        file_menu.addAction(save_action)

        save_as_action = QAction("Save &As...", self)
        save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as_action.triggered.connect(self._on_save_as)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        close_action = QAction("Close Window", self)
        close_action.setShortcut(QKeySequence.StandardKey.Close)
        close_action.triggered.connect(self.close)
        file_menu.addAction(close_action)

        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        edit_menu = self.menuBar().addMenu("&Edit")

        undo_action = self._undo_group.createUndoAction(self, "&Undo")
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        edit_menu.addAction(undo_action)

        redo_action = self._undo_group.createRedoAction(self, "&Redo")
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        edit_menu.addAction(redo_action)

        edit_menu.addSeparator()

        select_all_action = QAction("Select &All", self)
        select_all_action.setShortcut(QKeySequence.StandardKey.SelectAll)
        select_all_action.triggered.connect(self._on_select_all)
        edit_menu.addAction(select_all_action)

        self.select_linked_action = QAction("Select &Linked", self)
        self.select_linked_action.triggered.connect(self._on_select_linked)
        edit_menu.addAction(self.select_linked_action)
        edit_menu.aboutToShow.connect(self._update_select_linked_enabled)
        self._update_select_linked_enabled()

        edit_menu.addSeparator()

        self.pin_action = QAction(self)
        self.pin_action.setShortcut(QKeySequence("Ctrl+Shift+P"))
        self.pin_action.triggered.connect(self._on_toggle_pin)
        edit_menu.addAction(self.pin_action)
        edit_menu.aboutToShow.connect(self._update_pin_action)
        self._update_pin_action()

        view_menu = self.menuBar().addMenu("&View")

        self.view_canvas_action = QAction("Canvas", self)
        self.view_canvas_action.setCheckable(True)
        self.view_canvas_action.setShortcut(QKeySequence("Ctrl+1"))
        self.view_canvas_action.triggered.connect(
            lambda: self.tabs.setCurrentWidget(self.canvas_view)
        )
        view_menu.addAction(self.view_canvas_action)

        self.view_list_action = QAction("List", self)
        self.view_list_action.setCheckable(True)
        self.view_list_action.setShortcut(QKeySequence("Ctrl+2"))
        self.view_list_action.triggered.connect(
            lambda: self.tabs.setCurrentWidget(self.list_view)
        )
        view_menu.addAction(self.view_list_action)

        view_action_group = QActionGroup(self)
        view_action_group.setExclusive(True)
        view_action_group.addAction(self.view_canvas_action)
        view_action_group.addAction(self.view_list_action)

        view_menu.addSeparator()

        self.view_extents_action = QAction("Extents", self)
        self.view_extents_action.setShortcut(QKeySequence("Ctrl+0"))
        self.view_extents_action.triggered.connect(self._on_view_extents)
        view_menu.addAction(self.view_extents_action)

        view_menu.addSeparator()

        self.toggle_links_action = QAction(self)
        self.toggle_links_action.setShortcut(QKeySequence("Ctrl+Shift+L"))
        self.toggle_links_action.triggered.connect(self._on_toggle_links_visible)
        view_menu.addAction(self.toggle_links_action)
        self._update_toggle_links_action_text()

        view_menu.addSeparator()

        self.canvas_background_action = QAction("Canvas Background", self)
        self.canvas_background_action.triggered.connect(self._on_change_canvas_background)
        view_menu.addAction(self.canvas_background_action)

        arrange_menu = self.menuBar().addMenu("&Arrange")

        self.arrange_stacks_by_color_action = QAction("Stacks by Color", self)
        self.arrange_stacks_by_color_action.triggered.connect(
            lambda: self._run_auto_arrange("color")
        )
        arrange_menu.addAction(self.arrange_stacks_by_color_action)

        self.arrange_tile_action = QAction("Tile", self)
        self.arrange_tile_action.triggered.connect(lambda: self._run_auto_arrange("tile"))
        arrange_menu.addAction(self.arrange_tile_action)

        self.arrange_scatter_action = QAction("Scatter", self)
        self.arrange_scatter_action.triggered.connect(lambda: self._run_auto_arrange("scatter"))
        arrange_menu.addAction(self.arrange_scatter_action)

        arrange_menu.aboutToShow.connect(self._update_arrange_actions_enabled)
        self._update_arrange_actions_enabled()

        self.tabs.currentChanged.connect(self._on_current_tab_changed)
        self._on_current_tab_changed(self.tabs.currentIndex())

    def _on_current_tab_changed(self, index: int) -> None:
        if self.tabs.widget(index) is self.canvas_view:
            self.view_canvas_action.setChecked(True)
        elif self.tabs.widget(index) is self.list_view:
            self.view_list_action.setChecked(True)

    def _on_view_extents(self) -> None:
        self.canvas_view.fit_to_content(margin=VIEW_EXTENTS_MARGIN)

    def _on_toggle_links_visible(self) -> None:
        self._links_visible = not self._links_visible
        if self.canvas_scene is not None:
            self.canvas_scene.set_links_visible(self._links_visible)
        self._update_toggle_links_action_text()

    def _update_toggle_links_action_text(self) -> None:
        self.toggle_links_action.setText("Hide Links" if self._links_visible else "Show Links")

    def _on_select_all(self) -> None:
        if self.tabs.currentWidget() is self.canvas_view:
            if self.canvas_scene is not None:
                self.canvas_scene.select_all_cards()
        else:
            self.list_view.table_view.selectAll()

    def _update_select_linked_enabled(self) -> None:
        focused = self.canvas_scene.selected_card_id() if self.canvas_scene is not None else None
        self.select_linked_action.setEnabled(focused is not None)

    def _on_select_linked(self) -> None:
        if self.canvas_scene is None:
            return
        card_id = self.canvas_scene.selected_card_id()
        if card_id is None:
            return
        item = self.canvas_scene.item_for_card(card_id)
        if item is None:
            return
        self.tabs.setCurrentWidget(self.canvas_view)
        item.select_linked_graph()

    def _update_pin_action(self) -> None:
        card_ids = self.canvas_scene.selected_card_ids() if self.canvas_scene is not None else []
        self.pin_action.setEnabled(bool(card_ids))
        noun = "Card" if len(card_ids) == 1 else "Card(s)"
        verb = "Unpin" if card_ids and self.document.all_pinned(card_ids) else "Pin"
        self.pin_action.setText(f"{verb} {noun}")

    def _on_toggle_pin(self) -> None:
        if self.canvas_scene is None or self.undo_stack is None:
            return
        card_ids = self.canvas_scene.selected_card_ids()
        if not card_ids:
            return
        pin = not self.document.all_pinned(card_ids)
        self.undo_stack.push(TogglePinCommand(self.document, card_ids, pin))

    def _on_new(self) -> None:
        if self._window_manager is not None:
            self._window_manager.open_new_window()
        else:
            self._set_document(
                Document(
                    name="Untitled",
                    canvas_background_color=self._settings.default_background_color,
                ),
                path=None,
            )

    def _on_open(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(self, "Open File", "", FILE_DIALOG_FILTER)
        if not path_str:
            return
        path = Path(path_str)
        if self._window_manager is not None:
            self._window_manager.open_file(path, requesting_window=self)
        else:
            self.open_file(path)

    def _on_save(self) -> None:
        if self.document is None:
            return
        if self._current_path is None:
            self._on_save_as()
            return
        self._save_to(self._current_path)

    def _on_save_as(self) -> None:
        if self.document is None:
            return
        default_name = f"{self.document.name}.idxcards"
        path_str, _ = QFileDialog.getSaveFileName(
            self, "Save File As", default_name, FILE_DIALOG_FILTER
        )
        if not path_str:
            return
        path = Path(path_str)
        if path.suffix != ".idxcards":
            path = path.with_suffix(".idxcards")
        self._save_to(path)

    def _save_to(self, path: Path) -> None:
        try:
            save_document(self.document, path)
        except OSError as exc:
            QMessageBox.critical(self, "Failed to Save File", str(exc))
            return
        self._current_path = path
        self.undo_stack.setClean()
        self._update_title()

    @property
    def current_path(self) -> Path | None:
        return self._current_path

    def is_reusable(self) -> bool:
        """True for a blank, untouched Untitled window — no file path, no
        edits — the state File > Open should replace rather than leaving
        stranded as an extra empty window."""
        return self._current_path is None and (
            self.undo_stack is None or self.undo_stack.isClean()
        )

    def open_file(self, path: Path) -> None:
        try:
            document = load_document(path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Failed to Open File", str(exc))
            return
        self._set_document(document, path)

    def _set_document(self, document: Document, path: Path | None) -> None:
        old_stack = self.undo_stack
        old_model = self.card_table_model
        old_scene = self.canvas_scene

        self.undo_stack = QUndoStack(self)
        self._undo_group.addStack(self.undo_stack)
        self._activate_undo_stack()

        self.document = document
        self._current_path = path
        self.card_table_model = CardTableModel(document, undo_stack=self.undo_stack, parent=self)
        self.list_view.set_model(self.card_table_model)
        self.canvas_scene = CanvasScene(document, undo_stack=self.undo_stack, parent=self)
        self.canvas_scene.set_search_query(self._current_search_query)
        self.canvas_scene.set_links_visible(self._links_visible)
        self.canvas_view.setScene(self.canvas_scene)
        self.canvas_scene.selectionChanged.connect(self._on_canvas_selection_changed)
        self.undo_stack.cleanChanged.connect(self._update_title)
        self._update_title()
        self._update_arrange_actions_enabled()

        if old_model is not None:
            old_model.deleteLater()
        if old_scene is not None:
            old_scene.deleteLater()
        if old_stack is not None:
            old_stack.deleteLater()

    def _on_list_current_card_changed(self, card_id: str | None) -> None:
        if self._syncing_selection:
            return
        self._syncing_selection = True
        try:
            self._select_card_in_canvas(card_id)
        finally:
            self._syncing_selection = False

    def _on_canvas_selection_changed(self) -> None:
        card_id = self.canvas_scene.selected_card_id()
        if card_id is not None and card_id not in self.document.cards:
            # A cascading delete can fire selectionChanged (e.g. removing a
            # selected LinkItem) before the still-selected CardItem's own
            # cardRemoved signal has run — the item is still in the scene,
            # selected, but the Document has already dropped its data.
            card_id = None
        if self._syncing_selection:
            return
        self._syncing_selection = True
        try:
            self._select_card_in_list(card_id)
        finally:
            self._syncing_selection = False

    def _select_card_in_canvas(self, card_id: str | None) -> None:
        for item in self.canvas_scene.selectedItems():
            item.setSelected(False)
        if card_id is not None:
            item = self.canvas_scene.item_for_card(card_id)
            if item is not None:
                item.setSelected(True)

    def _select_card_in_list(self, card_id: str | None) -> None:
        table_view = self.list_view.table_view
        if card_id is None:
            table_view.clearSelection()
            table_view.setCurrentIndex(QModelIndex())
            return
        row = self.card_table_model.row_for_card_id(card_id)
        if row is None:
            return
        proxy_index = self.list_view.proxy_model.mapFromSource(self.card_table_model.index(row, 0))
        if not proxy_index.isValid():
            return  # filtered out by the current search query
        table_view.selectRow(proxy_index.row())

    def _focus_search_bar(self) -> None:
        self.search_bar.line_edit.setFocus()
        self.search_bar.line_edit.selectAll()

    def _on_create_card_shortcut(self) -> None:
        if self.card_table_model is None:
            return
        card_id = self.card_table_model.add_card()
        self._select_and_focus_new_card(card_id)

    def _select_and_focus_new_card(self, card_id: str | None) -> None:
        if card_id is None:
            return
        self._select_card_in_list(card_id)
        if self.tabs.currentWidget() is self.canvas_view:
            item = self.canvas_scene.item_for_card(card_id) if self.canvas_scene else None
            if item is not None:
                item.enter_edit_mode()
        else:
            self.list_view.edit_text_cell(card_id)

    def _on_search_query_changed(self, query: str) -> None:
        self._current_search_query = query
        self.list_view.set_search_query(query)
        if self.canvas_scene is not None:
            self.canvas_scene.set_search_query(query)

    def _on_link_requested(self, source_id: str, target_id: str) -> None:
        if self.document is None or self.undo_stack is None:
            return
        link_id = new_link_id(self.document.links.keys())
        link = Link(id=link_id, source=source_id, target=target_id)
        self.undo_stack.push(AddLinkCommand(self.document, link))

    def _on_canvas_delete_requested(self) -> None:
        if self.canvas_scene is None or self.undo_stack is None or self.document is None:
            return
        card_ids = self.canvas_scene.selected_card_ids()
        link_ids = self.canvas_scene.selected_link_ids()

        incident_link_count = 0
        if card_ids:
            card_id_set = set(card_ids)
            incident_link_ids = {
                link.id
                for link in self.document.links.values()
                if link.source in card_id_set or link.target in card_id_set
            }
            # Cards being deleted cascade their own incident links, so drop
            # those from the explicit link-deletion list to avoid deleting
            # the same link twice (the second delete would raise a KeyError).
            link_ids = [link_id for link_id in link_ids if link_id not in incident_link_ids]
            incident_link_count = len(incident_link_ids)
            if not confirm_delete_cards(self, len(card_ids), incident_link_count, self._settings):
                return

        if not card_ids and not link_ids:
            return

        total = len(card_ids) + len(link_ids)
        if total == 1:
            if card_ids:
                self.undo_stack.push(DeleteCardCommand(self.document, card_ids[0]))
            else:
                self.undo_stack.push(DeleteLinkCommand(self.document, link_ids[0]))
            return

        self.undo_stack.beginMacro(f"Delete {total} Item(s)")
        for card_id in card_ids:
            self.undo_stack.push(DeleteCardCommand(self.document, card_id))
        for link_id in link_ids:
            self.undo_stack.push(DeleteLinkCommand(self.document, link_id))
        self.undo_stack.endMacro()

    def _update_arrange_actions_enabled(self) -> None:
        unpinned_count = (
            sum(1 for card in self.document.iter_cards() if not card.pinned)
            if self.document is not None
            else 0
        )
        enabled = unpinned_count >= 2
        self.arrange_stacks_by_color_action.setEnabled(enabled)
        self.arrange_tile_action.setEnabled(enabled)
        self.arrange_scatter_action.setEnabled(enabled)

    def _run_auto_arrange(self, group_by: str) -> None:
        if self.document is None or self.undo_stack is None:
            return
        cards = list(self.document.iter_cards())
        if not cards or all(card.pinned for card in cards):
            return

        viewport_size = self.canvas_view.viewport().size()
        aspect_ratio = (
            viewport_size.width() / viewport_size.height() if viewport_size.height() else 1.0
        )
        new_positions = arrange_avoiding_pinned(cards, group_by, aspect_ratio=aspect_ratio)
        if not new_positions:
            return
        old_positions = {
            card_id: (self.document.get_card(card_id).x, self.document.get_card(card_id).y)
            for card_id in new_positions
        }
        self.undo_stack.push(AutoArrangeCommand(self.document, old_positions, new_positions))
        self.canvas_view.ensure_content_visible()

    def _on_change_canvas_background(self) -> None:
        if self.document is None or self.undo_stack is None:
            return
        old_color = self.document.canvas_background_color
        chosen = QColorDialog.getColor(QColor(old_color), self, "Canvas Background Color")
        if not chosen.isValid():
            return
        new_color = chosen.name()
        if new_color.lower() == old_color.lower():
            return
        self.undo_stack.push(ChangeCanvasBackgroundCommand(self.document, old_color, new_color))

    def _on_open_settings(self) -> None:
        dialog = SettingsDialog(
            self._settings.warn_before_delete, self._settings.default_background_color, self
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._settings.warn_before_delete = dialog.warn_before_delete()
        self._settings.default_background_color = dialog.default_background_color()

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        is_key_event = event.type() in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease)
        if is_key_event and not event.isAutoRepeat() and event.key() == Qt.Key.Key_Alt:
            if event.type() == QEvent.Type.KeyPress:
                if self.isActiveWindow():
                    self.canvas_view.link_controller.set_active(True)
            else:
                # Always deactivate on release, even if this window isn't
                # the active one right now — otherwise a window that lost
                # activation mid-hold (see changeEvent) could never get the
                # matching release to clear on its own.
                self.canvas_view.link_controller.set_active(False)
        return super().eventFilter(watched, event)

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange:
            if self.isActiveWindow():
                self._activate_undo_stack()
            else:
                # Guards against Link Mode getting stuck on: if the user
                # holds Option and switches away (Cmd-Tab, another window),
                # this app never sees the matching key-release event.
                self.canvas_view.link_controller.set_active(False)

    def _activate_undo_stack(self) -> None:
        if self.undo_stack is not None:
            self._undo_group.setActiveStack(self.undo_stack)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.undo_stack is not None and not self.undo_stack.isClean():
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                f"'{self.document.name}' has unsaved changes. Save before closing?",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if reply == QMessageBox.StandardButton.Save:
                self._on_save()
                if not self.undo_stack.isClean():
                    # Save As was cancelled, or the save failed; don't close.
                    event.ignore()
                    return

        QApplication.instance().removeEventFilter(self)
        if self._window_manager is not None:
            self._window_manager.forget_window(self)
        event.accept()

    def _update_title(self) -> None:
        if self.document is None:
            self.setWindowTitle("Index Cards")
            return
        dirty_marker = "" if self.undo_stack.isClean() else "*"
        self.setWindowTitle(f"Index Cards — {self.document.name}{dirty_marker}")
