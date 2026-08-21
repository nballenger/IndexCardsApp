from __future__ import annotations

from PySide6.QtGui import QUndoCommand

from indexcards.models.document import Document


class EditCardTextCommand(QUndoCommand):
    def __init__(self, document: Document, card_id: str, old_text: str, new_text: str) -> None:
        super().__init__("Edit Card Text")
        self._document = document
        self._card_id = card_id
        self._old_text = old_text
        self._new_text = new_text

    def redo(self) -> None:
        self._document.set_card_text(self._card_id, self._new_text)

    def undo(self) -> None:
        self._document.set_card_text(self._card_id, self._old_text)


class ChangeColorCommand(QUndoCommand):
    def __init__(self, document: Document, card_id: str, old_color: str, new_color: str) -> None:
        super().__init__("Change Card Color")
        self._document = document
        self._card_id = card_id
        self._old_color = old_color
        self._new_color = new_color

    def redo(self) -> None:
        self._document.set_card_color(self._card_id, self._new_color)

    def undo(self) -> None:
        self._document.set_card_color(self._card_id, self._old_color)


class ChangeTagsCommand(QUndoCommand):
    def __init__(
        self, document: Document, card_id: str, old_tags: list[str], new_tags: list[str]
    ) -> None:
        super().__init__("Change Card Tags")
        self._document = document
        self._card_id = card_id
        self._old_tags = list(old_tags)
        self._new_tags = list(new_tags)

    def redo(self) -> None:
        self._document.set_card_tags(self._card_id, self._new_tags)

    def undo(self) -> None:
        self._document.set_card_tags(self._card_id, self._old_tags)
