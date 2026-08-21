from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox

from indexcards.list_view.card_table_model import CardTableModel
from indexcards.list_view.list_view_widget import ListViewWidget
from indexcards.models.document import Document
from indexcards.persistence.file_io import load_document

FILE_DIALOG_FILTER = "Index Cards Files (*.idxcards);;All Files (*)"


class MainWindow(QMainWindow):
    """One window per open file."""

    def __init__(self) -> None:
        super().__init__()
        self.document: Document | None = None
        self.card_table_model: CardTableModel | None = None

        self.setWindowTitle("Index Cards")
        self.resize(1000, 700)

        self.list_view = ListViewWidget(self)
        self.setCentralWidget(self.list_view)

        self._build_menu()

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

        file_menu.addSeparator()

        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

    def _on_new(self) -> None:
        pass

    def _on_open(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(self, "Open File", "", FILE_DIALOG_FILTER)
        if not path_str:
            return
        self.open_file(Path(path_str))

    def _on_save(self) -> None:
        pass

    def open_file(self, path: Path) -> None:
        try:
            document = load_document(path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Failed to Open File", str(exc))
            return

        self.document = document
        self.card_table_model = CardTableModel(document, parent=self)
        self.list_view.set_model(self.card_table_model)
        self.setWindowTitle(f"Index Cards — {document.name}")
