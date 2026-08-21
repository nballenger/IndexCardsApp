from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QObject, Signal

from indexcards.models.card import Card
from indexcards.models.link import Link

DEFAULT_CANVAS_BACKGROUND_COLOR = "#3d6b4f"  # lowercase to match QColor.name()'s convention


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class Document(QObject):
    """Owns a file's cards and links. The sole path for mutating state.

    Every mutator below both changes state and emits the corresponding
    signal, so undo commands (later milestones) and views can never observe
    the model out of sync with these signals.
    """

    cardAdded = Signal(str)
    cardRemoved = Signal(str)
    cardChanged = Signal(str, object)  # card_id, frozenset[str] of changed fields
    cardMoved = Signal(str)
    cardsBulkMoved = Signal(object)  # list[str] of card_ids
    linkAdded = Signal(str)
    linkRemoved = Signal(str)
    dirtyChanged = Signal(bool)
    backgroundColorChanged = Signal(str)

    def __init__(self, name: str = "Untitled") -> None:
        super().__init__()
        self.name = name
        self.created_at = _now()
        self.modified_at = self.created_at
        self.cards: dict[str, Card] = {}
        self.links: dict[str, Link] = {}
        self.canvas_background_color = DEFAULT_CANVAS_BACKGROUND_COLOR
        self._dirty = False

    # -- dirty tracking --------------------------------------------------

    @property
    def dirty(self) -> bool:
        return self._dirty

    def _mark_dirty(self) -> None:
        self.modified_at = _now()
        if not self._dirty:
            self._dirty = True
            self.dirtyChanged.emit(True)

    def mark_clean(self) -> None:
        if self._dirty:
            self._dirty = False
            self.dirtyChanged.emit(False)

    # -- cards -------------------------------------------------------------

    def get_card(self, card_id: str) -> Card:
        return self.cards[card_id]

    def iter_cards(self):
        return iter(self.cards.values())

    def add_card(self, card: Card, index: int | None = None) -> None:
        """Adds a card, optionally re-inserting it at a specific position.

        `index` exists so DeleteCardCommand.undo() can restore a card to its
        original row rather than appending it at the end (Python dicts don't
        reorder on delete+re-add, so without this, undoing a delete would
        silently reorder the card list).
        """
        if card.id in self.cards:
            raise ValueError(f"card id already exists: {card.id}")
        if index is None or index >= len(self.cards):
            self.cards[card.id] = card
        else:
            items = list(self.cards.items())
            items.insert(index, (card.id, card))
            self.cards = dict(items)
        self._mark_dirty()
        self.cardAdded.emit(card.id)

    def remove_card(self, card_id: str) -> tuple[Card, list[Link]]:
        """Removes a card and cascades to remove any incident links.

        Returns the removed Card and the removed Links, so callers (undo
        commands) can restore both in one step.
        """
        card = self.cards.pop(card_id)
        removed_links = [
            link for link in self.links.values() if card_id in (link.source, link.target)
        ]
        for link in removed_links:
            del self.links[link.id]
        self._mark_dirty()
        for link in removed_links:
            self.linkRemoved.emit(link.id)
        self.cardRemoved.emit(card_id)
        return card, removed_links

    def set_card_text(self, card_id: str, text: str) -> None:
        text = text.strip()
        card = self.cards[card_id]
        if card.text == text:
            return
        card.text = text
        card.modified_at = _now()
        self._mark_dirty()
        self.cardChanged.emit(card_id, frozenset({"text"}))

    def set_card_color(self, card_id: str, color: str) -> None:
        card = self.cards[card_id]
        if card.color == color:
            return
        card.color = color
        card.modified_at = _now()
        self._mark_dirty()
        self.cardChanged.emit(card_id, frozenset({"color"}))

    def set_card_tags(self, card_id: str, tags: list[str]) -> None:
        card = self.cards[card_id]
        if card.tags == tags:
            return
        card.tags = list(tags)
        card.modified_at = _now()
        self._mark_dirty()
        self.cardChanged.emit(card_id, frozenset({"tags"}))

    def set_card_position(self, card_id: str, x: float, y: float) -> None:
        card = self.cards[card_id]
        if card.x == x and card.y == y:
            return
        card.x = x
        card.y = y
        self._mark_dirty()
        self.cardMoved.emit(card_id)

    def bulk_set_positions(self, positions: dict[str, tuple[float, float]]) -> None:
        moved_ids = []
        for card_id, (x, y) in positions.items():
            card = self.cards[card_id]
            if card.x == x and card.y == y:
                continue
            card.x = x
            card.y = y
            moved_ids.append(card_id)
        if not moved_ids:
            return
        self._mark_dirty()
        self.cardsBulkMoved.emit(moved_ids)

    # -- canvas appearance -----------------------------------------------------

    def set_canvas_background_color(self, color: str) -> None:
        if self.canvas_background_color.lower() == color.lower():
            return
        self.canvas_background_color = color
        self._mark_dirty()
        self.backgroundColorChanged.emit(color)

    # -- links ---------------------------------------------------------------

    def get_link(self, link_id: str) -> Link:
        return self.links[link_id]

    def iter_links(self):
        return iter(self.links.values())

    def add_link(self, link: Link) -> None:
        if link.id in self.links:
            raise ValueError(f"link id already exists: {link.id}")
        if link.source not in self.cards or link.target not in self.cards:
            raise ValueError(
                f"link {link.id} references a nonexistent card "
                f"(source={link.source}, target={link.target})"
            )
        self.links[link.id] = link
        self._mark_dirty()
        self.linkAdded.emit(link.id)

    def remove_link(self, link_id: str) -> Link:
        link = self.links.pop(link_id)
        self._mark_dirty()
        self.linkRemoved.emit(link_id)
        return link
