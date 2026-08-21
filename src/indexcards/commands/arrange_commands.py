from __future__ import annotations

from PySide6.QtGui import QUndoCommand

from indexcards.models.document import Document


class AutoArrangeCommand(QUndoCommand):
    """Repositions many cards atomically — one undo step for the whole rearrange."""

    def __init__(
        self,
        document: Document,
        old_positions: dict[str, tuple[float, float]],
        new_positions: dict[str, tuple[float, float]],
    ) -> None:
        super().__init__("Auto-Arrange")
        self._document = document
        self._old_positions = old_positions
        self._new_positions = new_positions

    def redo(self) -> None:
        self._document.bulk_set_positions(self._new_positions)

    def undo(self) -> None:
        self._document.bulk_set_positions(self._old_positions)
