from __future__ import annotations

from PySide6.QtGui import QUndoCommand

from indexcards.models.card import Card
from indexcards.models.document import Document
from indexcards.models.link import Link


class AddCardCommand(QUndoCommand):
    def __init__(self, document: Document, card: Card) -> None:
        super().__init__("Add Card")
        self._document = document
        self._card = card

    def redo(self) -> None:
        self._document.add_card(self._card)

    def undo(self) -> None:
        self._document.remove_card(self._card.id)


class DeleteCardCommand(QUndoCommand):
    """Deletes a card and cascades to any links incident on it.

    redo() captures whatever the Document actually removed (the card plus
    any incident links), so undo() can restore exactly that, in an order
    that tolerates other DeleteCardCommands for connected cards being
    undone earlier or later in the same macro.
    """

    def __init__(self, document: Document, card_id: str) -> None:
        super().__init__("Delete Card")
        self._document = document
        self._card_id = card_id
        self._card_index: int = 0
        self._removed_card: Card | None = None
        self._removed_links: list[Link] = []

    def redo(self) -> None:
        self._card_index = list(self._document.cards.keys()).index(self._card_id)
        self._removed_card, self._removed_links = self._document.remove_card(self._card_id)

    def undo(self) -> None:
        self._document.add_card(self._removed_card, index=self._card_index)
        for link in self._removed_links:
            self._document.add_link(link)


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
