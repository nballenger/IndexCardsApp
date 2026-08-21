from __future__ import annotations

from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import QGraphicsScene

from indexcards.canvas.card_item import CardItem
from indexcards.models.card import Card
from indexcards.models.document import Document


class CanvasScene(QGraphicsScene):
    """Mirrors a Document's cards as CardItems, staying in sync via signals."""

    def __init__(
        self, document: Document, undo_stack: QUndoStack | None = None, parent=None
    ) -> None:
        super().__init__(parent)
        self._document = document
        self._undo_stack = undo_stack
        self._items: dict[str, CardItem] = {}

        for card in document.iter_cards():
            self._add_item_for_card(card)

        document.cardAdded.connect(self._on_card_added)
        document.cardRemoved.connect(self._on_card_removed)
        document.cardChanged.connect(self._on_card_changed)
        document.cardMoved.connect(self._on_card_moved)
        document.cardsBulkMoved.connect(self._on_cards_bulk_moved)

    def item_for_card(self, card_id: str) -> CardItem | None:
        return self._items.get(card_id)

    def selected_card_id(self) -> str | None:
        for item in self.selectedItems():
            if isinstance(item, CardItem):
                return item.card_id
        return None

    def _add_item_for_card(self, card: Card) -> None:
        item = CardItem(card.id, self._document, undo_stack=self._undo_stack)
        item.setPos(card.x, card.y)
        self.addItem(item)
        self._items[card.id] = item

    def _on_card_added(self, card_id: str) -> None:
        self._add_item_for_card(self._document.get_card(card_id))

    def _on_card_removed(self, card_id: str) -> None:
        item = self._items.pop(card_id, None)
        if item is not None:
            self.removeItem(item)

    def _on_card_changed(self, card_id: str, fields: frozenset[str]) -> None:
        item = self._items.get(card_id)
        if item is not None:
            item.refresh()

    def _on_card_moved(self, card_id: str) -> None:
        item = self._items.get(card_id)
        if item is None:
            return
        card = self._document.get_card(card_id)
        item.setPos(card.x, card.y)

    def _on_cards_bulk_moved(self, card_ids: list[str]) -> None:
        for card_id in card_ids:
            self._on_card_moved(card_id)
