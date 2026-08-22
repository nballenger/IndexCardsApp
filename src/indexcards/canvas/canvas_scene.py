from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QUndoStack
from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsScene, QGraphicsSimpleTextItem

from indexcards.canvas.card_item import CardItem
from indexcards.canvas.link_item import LinkItem
from indexcards.commands.card_commands import AddCardCommand
from indexcards.models.card import DEFAULT_CARD_SIZE, Card
from indexcards.models.document import Document
from indexcards.models.link import Link
from indexcards.search import matches
from indexcards.utils.ids import new_card_id

_EMPTY_STATE_TEXT = "No cards yet — double-click here, or on the List tab, to create one."
_STACK_LABEL_Y_OFFSET = 28
_STACK_LABEL_PADDING = 4


class CanvasScene(QGraphicsScene):
    """Mirrors a Document's cards and links, staying in sync via signals."""

    def __init__(
        self, document: Document, undo_stack: QUndoStack | None = None, parent=None
    ) -> None:
        super().__init__(parent)
        self._document = document
        self._undo_stack = undo_stack
        self._items: dict[str, CardItem] = {}
        self._link_items: dict[str, LinkItem] = {}
        self._stack_labels: list[QGraphicsSimpleTextItem] = []
        self._search_query = ""
        self._links_visible = True

        for card in document.iter_cards():
            self._add_item_for_card(card)
        for link in document.iter_links():
            self._add_item_for_link(link)

        document.cardAdded.connect(self._on_card_added)
        document.cardRemoved.connect(self._on_card_removed)
        document.cardChanged.connect(self._on_card_changed)
        document.cardMoved.connect(self._on_card_moved)
        document.cardsBulkMoved.connect(self._on_cards_bulk_moved)
        document.linkAdded.connect(self._on_link_added)
        document.linkRemoved.connect(self._on_link_removed)
        document.backgroundColorChanged.connect(self._on_background_color_changed)

        self.setBackgroundBrush(QColor(document.canvas_background_color))

    def _on_background_color_changed(self, color: str) -> None:
        self.setBackgroundBrush(QColor(color))

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawBackground(painter, rect)
        if self._items:
            return
        painter.save()
        painter.setPen(QColor(150, 150, 150))
        # rect is whatever sub-region Qt is currently repainting (e.g. just
        # the area under a rubber-band drag, or a partial redraw after a
        # window-activation change) — not the visible viewport. Centering
        # the text in rect made it jump to a different position, sometimes
        # off-screen, on every partial repaint (and, since drawBackground
        # gets called once per incremental rubber-band frame, "painted" a
        # trail of mis-centered text fragments across the drag path).
        # Centering in the actual visible scene area instead keeps it
        # stable regardless of which sub-region is being redrawn — Qt still
        # only paints whatever part of it falls within rect.
        painter.drawText(
            self._visible_scene_rect(rect), Qt.AlignmentFlag.AlignCenter, _EMPTY_STATE_TEXT
        )
        painter.restore()

    def _visible_scene_rect(self, fallback: QRectF) -> QRectF:
        views = self.views()
        if not views:
            return fallback
        view = views[0]
        return view.mapToScene(view.viewport().rect()).boundingRect()

    def item_for_card(self, card_id: str) -> CardItem | None:
        return self._items.get(card_id)

    def add_card_at(self, x: float, y: float) -> str | None:
        """Creates a new card centered on (x, y) — used for double-click-to-
        create on empty canvas. Mirrors CardTableModel.add_card()'s pattern
        (id generation, default text, AddCardCommand push) but with an
        explicit position instead of a cascading default."""
        if self._undo_stack is None:
            return None
        card_id = new_card_id(self._document.cards.keys())
        card_count = len(self._document.cards)
        width, height = DEFAULT_CARD_SIZE
        card = Card(
            id=card_id,
            text=f"New Card {card_count + 1}",
            x=x - width / 2,
            y=y - height / 2,
        )
        self._undo_stack.push(AddCardCommand(self._document, card))
        return card_id

    def selected_card_id(self) -> str | None:
        for item in self.selectedItems():
            if isinstance(item, CardItem):
                return item.card_id
        return None

    def selected_card_ids(self) -> list[str]:
        return [item.card_id for item in self.selectedItems() if isinstance(item, CardItem)]

    def selected_link_ids(self) -> list[str]:
        return [item.link_id for item in self.selectedItems() if isinstance(item, LinkItem)]

    def select_all_cards(self) -> None:
        for item in self._items.values():
            item.setSelected(True)

    def show_tag_stack_labels(self, tag: str) -> None:
        """Draws a "Has <tag>" / "No <tag>" label above each cluster after
        an Auto-Arrange by tag. Purely a view-layer annotation (not part of
        the Document, never persisted) — cleared automatically the moment
        any card is added, removed, or moved, since at that point the
        labels no longer describe the actual layout."""
        self._clear_stack_labels()
        has_tag_cards = [card for card in self._document.iter_cards() if tag in card.tags]
        no_tag_cards = [card for card in self._document.iter_cards() if tag not in card.tags]
        for cards, label_text in ((has_tag_cards, f'Has "{tag}"'), (no_tag_cards, f'No "{tag}"')):
            if not cards:
                continue
            min_x = min(card.x for card in cards)
            min_y = min(card.y for card in cards)

            text_item = QGraphicsSimpleTextItem(label_text)
            text_item.setBrush(QColor(Qt.GlobalColor.black))
            text_bounds = text_item.boundingRect()

            chip = QGraphicsRectItem(
                0,
                0,
                text_bounds.width() + 2 * _STACK_LABEL_PADDING,
                text_bounds.height() + 2 * _STACK_LABEL_PADDING,
            )
            chip.setBrush(QColor(Qt.GlobalColor.white))
            chip.setPen(QPen(Qt.GlobalColor.darkGray, 1))
            chip.setPos(min_x, min_y - _STACK_LABEL_Y_OFFSET)

            text_item.setParentItem(chip)
            text_item.setPos(_STACK_LABEL_PADDING, _STACK_LABEL_PADDING)

            self.addItem(chip)
            self._stack_labels.append(chip)

    def _clear_stack_labels(self) -> None:
        for label in self._stack_labels:
            self.removeItem(label)
        self._stack_labels.clear()

    def set_links_visible(self, visible: bool) -> None:
        self._links_visible = visible
        for link_item in self._link_items.values():
            link_item.setVisible(visible)

    def set_search_query(self, query: str) -> None:
        self._search_query = query
        for item in self._items.values():
            self._apply_dim(item)
        for link_item in self._link_items.values():
            self._apply_link_dim(link_item)

    def _card_matches(self, card_id: str) -> bool:
        return matches(self._document.get_card(card_id), self._search_query)

    def _apply_dim(self, item: CardItem) -> None:
        item.set_dimmed(not self._card_matches(item.card_id))

    def _apply_link_dim(self, link_item: LinkItem) -> None:
        link = self._document.get_link(link_item.link_id)
        both_match = self._card_matches(link.source) and self._card_matches(link.target)
        link_item.set_dimmed(not both_match)

    def _add_item_for_card(self, card: Card) -> None:
        item = CardItem(card.id, self._document, undo_stack=self._undo_stack)
        item.setPos(card.x, card.y)
        self.addItem(item)
        self._items[card.id] = item
        self._apply_dim(item)

    def _add_item_for_link(self, link: Link) -> None:
        source_item = self._items.get(link.source)
        target_item = self._items.get(link.target)
        if source_item is None or target_item is None:
            return
        item = LinkItem(link.id, source_item, target_item)
        self.addItem(item)
        self._link_items[link.id] = item
        self._apply_link_dim(item)
        item.setVisible(self._links_visible)

    def _on_card_added(self, card_id: str) -> None:
        self._clear_stack_labels()
        self._add_item_for_card(self._document.get_card(card_id))

    def _on_card_removed(self, card_id: str) -> None:
        self._clear_stack_labels()
        item = self._items.pop(card_id, None)
        if item is not None:
            self.removeItem(item)

    def _on_card_changed(self, card_id: str, fields: frozenset[str]) -> None:
        item = self._items.get(card_id)
        if item is not None:
            item.refresh()
            if fields & {"text", "tags"}:
                self._apply_dim(item)
                for link_item in self._link_items.values():
                    link = self._document.get_link(link_item.link_id)
                    if card_id in (link.source, link.target):
                        self._apply_link_dim(link_item)

    def _on_card_moved(self, card_id: str) -> None:
        self._clear_stack_labels()
        item = self._items.get(card_id)
        if item is None:
            return
        card = self._document.get_card(card_id)
        item.setPos(card.x, card.y)

    def _on_cards_bulk_moved(self, card_ids: list[str]) -> None:
        # Cleared once here rather than once per card inside the loop below
        # (which would just re-clear an already-empty list on every
        # iteration) — the caller (MainWindow._on_auto_arrange) re-adds the
        # labels itself, after this signal has finished firing.
        self._clear_stack_labels()
        for card_id in card_ids:
            item = self._items.get(card_id)
            if item is None:
                continue
            card = self._document.get_card(card_id)
            item.setPos(card.x, card.y)

    def _on_link_added(self, link_id: str) -> None:
        self._add_item_for_link(self._document.get_link(link_id))

    def _on_link_removed(self, link_id: str) -> None:
        item = self._link_items.pop(link_id, None)
        if item is not None:
            item.disconnect_listeners()
            self.removeItem(item)
