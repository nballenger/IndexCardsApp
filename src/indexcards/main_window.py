from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QAction, QKeySequence, QUndoGroup, QUndoStack
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox, QTabWidget

from indexcards.canvas.canvas_scene import CanvasScene
from indexcards.canvas.canvas_view import CanvasView
from indexcards.list_view.card_table_model import CardTableModel
from indexcards.list_view.list_view_widget import ListViewWidget
from indexcards.models.document import Document
from indexcards.persistence.file_io import load_document, save_document

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

        self.setWindowTitle("Index Cards")
        self.resize(1000, 700)

        self.canvas_view = CanvasView(self)
        self.list_view = ListViewWidget(self)
        self.tabs = QTabWidget(self)
        self.tabs.addTab(self.canvas_view, "Canvas")
        self.tabs.addTab(self.list_view, "List")
        self.setCentralWidget(self.tabs)

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
        self.canvas_scene = CanvasScene(document, parent=self)
        self.canvas_view.setScene(self.canvas_scene)
        self.undo_stack.cleanChanged.connect(self._update_title)
        self._update_title()

        if old_model is not None:
            old_model.deleteLater()
        if old_scene is not None:
            old_scene.deleteLater()
        if old_stack is not None:
            old_stack.deleteLater()

    def _update_title(self) -> None:
        if self.document is None:
            self.setWindowTitle("Index Cards")
            return
        dirty_marker = "" if self.undo_stack.isClean() else "*"
        self.setWindowTitle(f"Index Cards — {self.document.name}{dirty_marker}")
