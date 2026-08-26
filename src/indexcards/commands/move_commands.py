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


class MoveCardsCommand(QUndoCommand):
    """Repositions several cards atomically, as one undo step — for an
    ordinary multi-card drag (as opposed to AutoArrangeCommand, which is
    for an Auto-Arrange run; kept as a separate command so the Undo menu
    doesn't misleadingly say "Undo Auto-Arrange" after a plain drag)."""

    def __init__(
        self,
        document: Document,
        old_positions: dict[str, tuple[float, float]],
        new_positions: dict[str, tuple[float, float]],
    ) -> None:
        super().__init__("Move Cards")
        self._document = document
        self._old_positions = old_positions
        self._new_positions = new_positions

    def redo(self) -> None:
        self._document.bulk_set_positions(self._new_positions)

    def undo(self) -> None:
        self._document.bulk_set_positions(self._old_positions)


class MoveStackCommand(QUndoCommand):
    def __init__(
        self,
        document: Document,
        stack_id: str,
        old_pos: tuple[float, float],
        new_pos: tuple[float, float],
    ) -> None:
        super().__init__("Move Stack")
        self._document = document
        self._stack_id = stack_id
        self._old_pos = old_pos
        self._new_pos = new_pos

    def redo(self) -> None:
        self._document.set_stack_position(self._stack_id, *self._new_pos)

    def undo(self) -> None:
        self._document.set_stack_position(self._stack_id, *self._old_pos)
