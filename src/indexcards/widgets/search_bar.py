from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QWidget

from indexcards.feature_flags import TAGS_ENABLED


class SearchBar(QWidget):
    queryChanged = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.line_edit = QLineEdit(self)
        placeholder = "Search text and tags…" if TAGS_ENABLED else "Search text…"
        self.line_edit.setPlaceholderText(placeholder)
        self.line_edit.setClearButtonEnabled(True)
        self.line_edit.textChanged.connect(self.queryChanged)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.line_edit)
