from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtGui import QAction, QKeySequence, QUndoGroup, QUndoStack
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QToolBar,
)

from indexcards.canvas.canvas_scene import CanvasScene
from indexcards.canvas.canvas_view import CanvasView
from indexcards.commands.card_commands import DeleteCardCommand
from indexcards.commands.link_commands import AddLinkCommand, DeleteLinkCommand
from indexcards.list_view.card_table_model import CardTableModel
from indexcards.list_view.list_view_widget import ListViewWidget
from indexcards.models.document import Document
from indexcards.models.link import Link
from indexcards.persistence.file_io import load_document, save_document
from indexcards.utils.ids import new_link_id
from indexcards.widgets.dialogs import confirm_delete_cards
from indexcards.widgets.markdown_editor import MarkdownEditorWidget

FILE_DIALOG_FILTER = "Index Cards Files (*.idxcards);;All Files (*)"


class MainWindow(QMainWindow):
    """One window per open file."""

    def __init__(self, undo_group: QUndoGroup | None = None) -> None:
        super().__init__()
        self._undo_group = undo_group if undo_group is not None else QUndoGroup(self)

        self.document: Document | None = None
        self.card_table_model: CardTableModel | None = None
        self.canvas_scene: CanvasScene | None = None
        self.undo_stack: QUndoStack | None = None
        self._current_path: Path | None = None
        self._syncing_selection = False

        self.setWindowTitle("Index Cards")
        self.resize(1000, 700)

        self.canvas_view = CanvasView(self)
        self.list_view = ListViewWidget(self)
        self.tabs = QTabWidget(self)
        self.tabs.addTab(self.canvas_view, "Canvas")
        self.tabs.addTab(self.list_view, "List")
        self.setCentralWidget(self.tabs)

        self.markdown_editor = MarkdownEditorWidget(self)
        self.editor_dock = QDockWidget("Card Text", self)
        self.editor_dock.setWidget(self.markdown_editor)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.editor_dock)

        self.list_view.currentCardChanged.connect(self._on_list_current_card_changed)
        self.canvas_view.link_controller.linkRequested.connect(self._on_link_requested)
        self.canvas_view.deleteRequested.connect(self._on_canvas_delete_requested)

        self.canvas_toolbar = QToolBar("Canvas Tools", self)
        self.link_mode_action = QAction("Link Mode", self)
        self.link_mode_action.setCheckable(True)
        self.link_mode_action.setToolTip("Drag from one card to another to link them")
        self.link_mode_action.toggled.connect(self.canvas_view.link_controller.set_active)
        self.canvas_toolbar.addAction(self.link_mode_action)
        self.addToolBar(self.canvas_toolbar)
        canvas_tab_index = self.tabs.indexOf(self.canvas_view)
        self.tabs.currentChanged.connect(
            lambda index: self.canvas_toolbar.setVisible(index == canvas_tab_index)
        )

        self._build_menu()
        self._set_document(Document(name="Untitled"), path=None)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")

        new_action = QAction("&New", self)
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

    def _on_new(self) -> None:
        self._set_document(Document(name="Untitled"), path=None)

    def _on_open(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(self, "Open File", "", FILE_DIALOG_FILTER)
        if not path_str:
            return
        self.open_file(Path(path_str))

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
        self._undo_group.setActiveStack(self.undo_stack)

        self.document = document
        self._current_path = path
        self.card_table_model = CardTableModel(document, undo_stack=self.undo_stack, parent=self)
        self.list_view.set_model(self.card_table_model)
        self.canvas_scene = CanvasScene(document, undo_stack=self.undo_stack, parent=self)
        self.canvas_view.setScene(self.canvas_scene)
        self.canvas_scene.selectionChanged.connect(self._on_canvas_selection_changed)
        self.markdown_editor.set_card(document, self.undo_stack, None)
        self.undo_stack.cleanChanged.connect(self._update_title)
        self._update_title()

        if old_model is not None:
            old_model.deleteLater()
        if old_scene is not None:
            old_scene.deleteLater()
        if old_stack is not None:
            old_stack.deleteLater()

    def _on_list_current_card_changed(self, card_id: str | None) -> None:
        self.markdown_editor.set_card(self.document, self.undo_stack, card_id)
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
        self.markdown_editor.set_card(self.document, self.undo_stack, card_id)
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
        table_view.selectRow(row)

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
            if not confirm_delete_cards(self, len(card_ids), incident_link_count):
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

    def _update_title(self) -> None:
        if self.document is None:
            self.setWindowTitle("Index Cards")
            return
        dirty_marker = "" if self.undo_stack.isClean() else "*"
        self.setWindowTitle(f"Index Cards — {self.document.name}{dirty_marker}")
