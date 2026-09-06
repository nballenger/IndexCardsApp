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
    def __init__(
        self, document: Document, card_id: str, old_slot_id: str, new_slot_id: str
    ) -> None:
        super().__init__("Change Card Color")
        self._document = document
        self._card_id = card_id
        self._old_slot_id = old_slot_id
        self._new_slot_id = new_slot_id

    def redo(self) -> None:
        self._document.set_card_color_slot(self._card_id, self._new_slot_id)

    def undo(self) -> None:
        self._document.set_card_color_slot(self._card_id, self._old_slot_id)


class ChangeColorsCommand(QUndoCommand):
    """Sets color_slot on every card in card_ids to the same new value, as
    one undo step, restoring each card's own prior color individually on
    undo (a mixed selection's "before" isn't uniform) — mirrors
    TogglePinCommand exactly. Used whenever a color choice can apply to a
    multi-card selection (the canvas context menu, Edit > Card Color);
    ChangeColorCommand itself stays in use for the List view's single-row
    color-cell edit, which is never selection-scoped."""

    def __init__(self, document: Document, card_ids: list[str], new_slot_id: str) -> None:
        super().__init__("Change Card Color" if len(card_ids) == 1 else "Change Cards Color")
        self._document = document
        self._card_ids = list(card_ids)
        self._new_slot_id = new_slot_id
        self._old_slots = {
            card_id: document.get_card(card_id).color_slot for card_id in self._card_ids
        }

    def redo(self) -> None:
        for card_id in self._card_ids:
            self._document.set_card_color_slot(card_id, self._new_slot_id)

    def undo(self) -> None:
        for card_id, old_slot_id in self._old_slots.items():
            self._document.set_card_color_slot(card_id, old_slot_id)


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


class TogglePinCommand(QUndoCommand):
    """Pins or unpins every card in card_ids as one undo step.

    redo() sets them all to the same target `pinned` value (mixed
    selections all end up pinned; an all-pinned selection ends up
    unpinned — the caller decides which via `pinned`). undo() restores
    each card's own prior state individually, since a mixed selection's
    "before" isn't uniform.
    """

    def __init__(self, document: Document, card_ids: list[str], pinned: bool) -> None:
        super().__init__("Pin Cards" if pinned else "Unpin Cards")
        self._document = document
        self._card_ids = list(card_ids)
        self._pinned = pinned
        self._old_states = {
            card_id: document.get_card(card_id).pinned for card_id in self._card_ids
        }

    def redo(self) -> None:
        for card_id in self._card_ids:
            self._document.set_card_pinned(card_id, self._pinned)

    def undo(self) -> None:
        for card_id, old_pinned in self._old_states.items():
            self._document.set_card_pinned(card_id, old_pinned)
