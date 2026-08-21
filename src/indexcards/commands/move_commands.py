from __future__ import annotations

from PySide6.QtGui import QUndoCommand

from indexcards.models.document import Document


class MoveCardCommand(QUndoCommand):
    def __init__(
        self,
        document: Document,
        card_id: str,
        old_pos: tuple[float, float],
        new_pos: tuple[float, float],
    ) -> None:
        super().__init__("Move Card")
        self._document = document
        self._card_id = card_id
        self._old_pos = old_pos
        self._new_pos = new_pos

    def redo(self) -> None:
        self._document.set_card_position(self._card_id, *self._new_pos)

    def undo(self) -> None:
        self._document.set_card_position(self._card_id, *self._old_pos)
