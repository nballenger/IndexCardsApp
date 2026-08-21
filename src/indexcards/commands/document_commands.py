from __future__ import annotations

from PySide6.QtGui import QUndoCommand

from indexcards.models.document import Document


class ChangeCanvasBackgroundCommand(QUndoCommand):
    def __init__(self, document: Document, old_color: str, new_color: str) -> None:
        super().__init__("Change Canvas Background")
        self._document = document
        self._old_color = old_color
        self._new_color = new_color

    def redo(self) -> None:
        self._document.set_canvas_background_color(self._new_color)

    def undo(self) -> None:
        self._document.set_canvas_background_color(self._old_color)
