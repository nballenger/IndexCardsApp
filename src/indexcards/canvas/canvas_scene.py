from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QUndoStack
from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsScene, QGraphicsSimpleTextItem

from indexcards.canvas.card_item import CardItem
from indexcards.canvas.link_item import LinkItem
from indexcards.canvas.stack_item import StackItem
from indexcards.commands.card_commands import AddCardCommand
from indexcards.models.card import DEFAULT_CARD_SIZE, Card
from indexcards.models.document import Document
from indexcards.models.link import Link
from indexcards.models.stack import Stack
from indexcards.search import matches
from indexcards.utils.ids import new_card_id

_EMPTY_STATE_TEXT = "No cards yet — double-click here, or on the List tab, to create one."
_STACK_LABEL_Y_OFFSET = 28
_STACK_LABEL_PADDING = 4


class CanvasScene(QGraphicsScene):
    """Mirrors a Document's cards and links, staying in sync via signals."""

    # Emitted whenever a card is added, removed, or (re)positioned — i.e.
    # whenever itemsBoundingRect() may have changed. CanvasView listens so
    # it can keep its pannable sceneRect margin centered on the content.
    contentBoundsChanged = Signal()

    def __init__(
        self, document: Document, undo_stack: QUndoStack | None = None, parent=None
    ) -> None:
        super().__init__(parent)
        self._document = document
        self._undo_stack = undo_stack
        self._items: dict[str, CardItem] = {}
        self._link_items: dict[str, LinkItem] = {}
        self._stack_items: dict[str, StackItem] = {}  # Stack objects (this feature)
        self._stack_labels: list[QGraphicsSimpleTextItem] = []  # unrelated: tag-cascade labels
        self._search_query = ""
        self._links_visible = True
        self._links_emphasized = False
        self._link_mode_active = False
        # Cards/Stacks have no persisted stacking order — visual overlap is
        # purely a view-layer QGraphicsItem.zValue() concern, raised on
        # press (see bring_item_to_front) and here on creation, using an
        # always-increasing counter so "bring to front" always outranks
        # whatever was raised before it. Never saved to the document.
        self._next_z_value = 0.0

        for card in document.iter_cards():
            self._add_item_for_card(card)
        for link in document.iter_links():
            self._add_item_for_link(link)
        for stack in document.iter_stacks():
            self._add_item_for_stack(stack)

        document.cardAdded.connect(self._on_card_added)
        document.cardRemoved.connect(self._on_card_removed)
        document.cardChanged.connect(self._on_card_changed)
        document.cardMoved.connect(self._on_card_moved)
        document.cardsBulkMoved.connect(self._on_cards_bulk_moved)
        document.linkAdded.connect(self._on_link_added)
        document.linkRemoved.connect(self._on_link_removed)
        document.linkChanged.connect(self._on_link_changed)
        document.stackAdded.connect(self._on_stack_added)
        document.stackRemoved.connect(self._on_stack_removed)
        document.stackChanged.connect(self._on_stack_changed)
        document.stackMoved.connect(self._on_stack_moved)
        document.stacksBulkMoved.connect(self._on_stacks_bulk_moved)
        document.backgroundColorChanged.connect(self._on_background_color_changed)
        document.themeChanged.connect(self._on_theme_changed)
        document.themeSlotChanged.connect(self._on_theme_slot_changed)
        document.linkColorModeChanged.connect(self._on_link_style_changed)
        document.linkWeightChanged.connect(self._on_link_style_changed)

        self.setBackgroundBrush(QColor(document.canvas_background_color))

    @property
    def document(self) -> Document:
        return self._document

    def _on_background_color_changed(self, color: str) -> None:
        self.setBackgroundBrush(QColor(color))

    def _on_theme_changed(self) -> None:
        # A whole-theme replacement (switching themes, or editing the
        # current theme's background via the Theme Editor) only emits
        # themeChanged, never backgroundColorChanged (that signal is
        # specific to set_canvas_background_color, the single-field
        # mutator "Canvas Background..." uses) — so the brush needs its
        # own refresh here too, not just each card.
        self.setBackgroundBrush(QColor(self._document.canvas_background_color))
        for item in self._items.values():
            item.refresh()
        for link_item in self._link_items.values():
            link_item.refresh()

    def _on_theme_slot_changed(self, slot_id: str) -> None:
        for item in self._items.values():
            item.refresh()

    def _on_link_style_changed(self, _value=None) -> None:
        for link_item in self._link_items.values():
            link_item.refresh()

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawBackground(painter, rect)
        if self._items or self._stack_items:
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

    def item_for_stack(self, stack_id: str) -> StackItem | None:
        return self._stack_items.get(stack_id)

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
            color_slot=self._document.theme.slots[0].id,
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

    def selected_stack_ids(self) -> list[str]:
        return [item.stack_id for item in self.selectedItems() if isinstance(item, StackItem)]

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

    def set_links_emphasized(self, emphasized: bool) -> None:
        self._links_emphasized = emphasized
        for link_item in self._link_items.values():
            link_item.set_emphasized(emphasized)

    def set_link_mode_active(self, active: bool) -> None:
        self._link_mode_active = active
        for item in self._items.values():
            item.set_link_mode_active(active)

    def set_search_query(self, query: str) -> None:
        self._search_query = query
        for item in self._items.values():
            self._apply_dim(item)
        for link_item in self._link_items.values():
            self._apply_link_dim(link_item)
        for stack_item in self._stack_items.values():
            self._apply_stack_dim(stack_item)

    def _card_matches(self, card_id: str) -> bool:
        return matches(self._document.get_card(card_id), self._search_query)

    def _apply_dim(self, item: CardItem) -> None:
        item.set_dimmed(not self._card_matches(item.card_id))

    def _apply_link_dim(self, link_item: LinkItem) -> None:
        link = self._document.get_link(link_item.link_id)
        both_match = self._card_matches(link.source) and self._card_matches(link.target)
        link_item.set_dimmed(not both_match)

    def _apply_stack_dim(self, item: StackItem) -> None:
        if not self._search_query:
            item.set_search_match_count(None)
            return
        stack = self._document.get_stack(item.stack_id)
        matching = sum(1 for card_id in stack.card_ids if self._card_matches(card_id))
        item.set_search_match_count(matching)

    def bring_item_to_front(self, item: CardItem | StackItem) -> None:
        """Raises item above everything else on the canvas — and, if it's
        part of a multi-selection, every other selected Card/Stack right
        alongside it, so dragging a group keeps the whole group together
        on top rather than just the one item that happened to be pressed.
        Called on press (see CardItem/StackItem.mousePressEvent) and on
        creation, so a card that's about to be looked at or edited is
        never left hidden behind something else. Pure view state — never
        saved, and z-order resets to creation order on reload."""
        if item.isSelected():
            targets = [
                selected
                for selected in self.selectedItems()
                if isinstance(selected, (CardItem, StackItem))
            ]
        else:
            targets = [item]
        for target in targets:
            self._next_z_value += 1
            target.setZValue(self._next_z_value)

    def _add_item_for_card(self, card: Card) -> None:
        if card.stack_id is not None:
            # Stacked cards are represented only by their Stack's own
            # StackItem — they never get a CardItem of their own while a
            # member of a stack.
            return
        item = CardItem(card.id, self._document, undo_stack=self._undo_stack)
        item.setPos(card.x, card.y)
        self.addItem(item)
        self._items[card.id] = item
        self._apply_dim(item)
        item.set_link_mode_active(self._link_mode_active)
        self.bring_item_to_front(item)

    def _add_item_for_stack(self, stack: Stack) -> None:
        item = StackItem(stack.id, self._document, undo_stack=self._undo_stack)
        item.setPos(stack.x, stack.y)
        self.addItem(item)
        self._stack_items[stack.id] = item
        self.bring_item_to_front(item)
        self._apply_stack_dim(item)

    def _sync_card_visibility(self, card_id: str) -> None:
        """Called when a card's stack_id changes: removes its CardItem if
        it just joined a stack, or (re)creates one if it just left a
        stack (e.g. Explode)."""
        card = self._document.get_card(card_id)
        if card.stack_id is not None:
            item = self._items.pop(card_id, None)
            if item is not None:
                self.removeItem(item)
            stack_item = self._stack_items.get(card.stack_id)
            if stack_item is not None:
                self._apply_stack_dim(stack_item)
        elif card_id not in self._items:
            self._add_item_for_card(card)
        self._refresh_empty_state()
        self.contentBoundsChanged.emit()

    def _refresh_empty_state(self) -> None:
        """Forces a full repaint so the "no cards yet" placeholder
        appears/disappears immediately whenever the scene transitions
        to/from having zero items — not just whatever narrower region Qt
        would otherwise invalidate on its own for one added/removed item
        (e.g. adding a card only invalidates that card's own bounds,
        leaving the rest of the previously-drawn placeholder text stale
        until some unrelated repaint, like a window-activation change,
        happens to redraw the whole viewport)."""
        self.update()

    def _add_item_for_link(self, link: Link, *, is_new: bool = False) -> None:
        source_item = self._items.get(link.source)
        target_item = self._items.get(link.target)
        if source_item is None or target_item is None:
            return
        item = LinkItem(link.id, source_item, target_item, self._document, self._undo_stack)
        self.addItem(item)
        self._link_items[link.id] = item
        self._apply_link_dim(item)
        if self._links_visible:
            item.setVisible(True)
            item.set_emphasized(self._links_emphasized)
        elif is_new:
            self._flash_new_link(item)
        else:
            item.setVisible(False)

    def _flash_new_link(self, item: LinkItem) -> None:
        """A link created (is_new=True, i.e. via the linkAdded signal --
        never the initial bulk population in __init__) while Links are
        hidden would otherwise just vanish silently, with no sign it was
        ever made. Shows it and lets LinkItem run its own grow/fade
        animation (see LinkItem.start_flash), then hides it for real
        once that finishes. _end_link_flash reads self._links_visible/
        self._links_emphasized fresh rather than assuming they're
        unchanged, so toggling Links on (or on-and-emphasized) mid-flash
        correctly leaves this link showing that way instead of blinking
        it off regardless."""
        item.setVisible(True)
        item.start_flash(on_finished=lambda: self._end_link_flash(item))

    def _end_link_flash(self, item: LinkItem) -> None:
        if item.scene() is None:
            return  # this link (or one of its cards) was deleted mid-flash
        item.setVisible(self._links_visible)
        item.set_emphasized(self._links_emphasized)

    def _on_card_added(self, card_id: str) -> None:
        self._clear_stack_labels()
        self._add_item_for_card(self._document.get_card(card_id))
        self._refresh_empty_state()
        self.contentBoundsChanged.emit()

    def _on_card_removed(self, card_id: str) -> None:
        self._clear_stack_labels()
        item = self._items.pop(card_id, None)
        if item is not None:
            self.removeItem(item)
        self._refresh_empty_state()
        self.contentBoundsChanged.emit()

    def _on_card_changed(self, card_id: str, fields: frozenset[str]) -> None:
        if "stack_id" in fields:
            self._sync_card_visibility(card_id)
            return
        item = self._items.get(card_id)
        if item is not None:
            item.refresh()
            if fields & {"text", "tags"}:
                self._apply_dim(item)
                for link_item in self._link_items.values():
                    link = self._document.get_link(link_item.link_id)
                    if card_id in (link.source, link.target):
                        self._apply_link_dim(link_item)
        elif fields & {"text", "tags"}:
            # A stacked card has no CardItem of its own — its text/tags
            # still affect whether its Stack counts as a search match.
            card = self._document.get_card(card_id)
            stack_item = (
                self._stack_items.get(card.stack_id) if card.stack_id is not None else None
            )
            if stack_item is not None:
                self._apply_stack_dim(stack_item)

    def _on_card_moved(self, card_id: str) -> None:
        self._clear_stack_labels()
        item = self._items.get(card_id)
        if item is None:
            return
        card = self._document.get_card(card_id)
        item.setPos(card.x, card.y)
        self.contentBoundsChanged.emit()

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
        self.contentBoundsChanged.emit()

    def _on_link_added(self, link_id: str) -> None:
        self._add_item_for_link(self._document.get_link(link_id), is_new=True)

    def _on_link_removed(self, link_id: str) -> None:
        item = self._link_items.pop(link_id, None)
        if item is not None:
            item.disconnect_listeners()
            self.removeItem(item)

    def _on_link_changed(self, link_id: str, fields: frozenset[str]) -> None:
        item = self._link_items.get(link_id)
        if item is not None:
            item.refresh()

    def _on_stack_added(self, stack_id: str) -> None:
        self._add_item_for_stack(self._document.get_stack(stack_id))
        self._refresh_empty_state()
        self.contentBoundsChanged.emit()

    def _on_stack_removed(self, stack_id: str) -> None:
        item = self._stack_items.pop(stack_id, None)
        if item is not None:
            self.removeItem(item)
        self._refresh_empty_state()
        self.contentBoundsChanged.emit()

    def _on_stack_changed(self, stack_id: str, fields: frozenset[str]) -> None:
        item = self._stack_items.get(stack_id)
        if item is not None:
            item.refresh()
            # Covers membership changes (card_ids) — a member joining or
            # leaving changes how many matches the badge should show.
            self._apply_stack_dim(item)

    def _on_stack_moved(self, stack_id: str) -> None:
        item = self._stack_items.get(stack_id)
        if item is None:
            return
        stack = self._document.get_stack(stack_id)
        item.setPos(stack.x, stack.y)
        self.contentBoundsChanged.emit()

    def _on_stacks_bulk_moved(self, stack_ids: list[str]) -> None:
        for stack_id in stack_ids:
            item = self._stack_items.get(stack_id)
            if item is None:
                continue
            stack = self._document.get_stack(stack_id)
            item.setPos(stack.x, stack.y)
        self.contentBoundsChanged.emit()
