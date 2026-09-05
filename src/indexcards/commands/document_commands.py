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


class ChangeLinkColorModeCommand(QUndoCommand):
    def __init__(self, document: Document, old_mode: str, new_mode: str) -> None:
        super().__init__("Change Link Color")
        self._document = document
        self._old_mode = old_mode
        self._new_mode = new_mode

    def redo(self) -> None:
        self._document.set_theme_link_color_mode(self._new_mode)

    def undo(self) -> None:
        self._document.set_theme_link_color_mode(self._old_mode)


class ChangeLinkWeightCommand(QUndoCommand):
    def __init__(self, document: Document, old_weight: int, new_weight: int) -> None:
        super().__init__("Change Link Weight")
        self._document = document
        self._old_weight = old_weight
        self._new_weight = new_weight

    def redo(self) -> None:
        self._document.set_theme_link_weight(self._new_weight)

    def undo(self) -> None:
        self._document.set_theme_link_weight(self._old_weight)


class ChangeDefaultLineEndingCommand(QUndoCommand):
    def __init__(self, document: Document, old_ending: str, new_ending: str) -> None:
        super().__init__("Change Default Line Ending")
        self._document = document
        self._old_ending = old_ending
        self._new_ending = new_ending

    def redo(self) -> None:
        self._document.set_default_line_ending(self._new_ending)

    def undo(self) -> None:
        self._document.set_default_line_ending(self._old_ending)
