from __future__ import annotations

from PySide6.QtGui import QUndoCommand

from indexcards.models.document import Document
from indexcards.models.theme import Theme


class SetDocumentThemeCommand(QUndoCommand):
    """Backs every whole-theme replacement: committing Theme Editor edits,
    switching to a different theme, and undo/redo of both — a single
    shared command rather than one per trigger, since they're all "swap
    self.theme wholesale" at the model level."""

    def __init__(self, document: Document, old_theme: Theme, new_theme: Theme) -> None:
        super().__init__("Change Theme")
        self._document = document
        self._old_theme = old_theme
        self._new_theme = new_theme

    def redo(self) -> None:
        self._document.set_theme_snapshot(self._new_theme)

    def undo(self) -> None:
        self._document.set_theme_snapshot(self._old_theme)
