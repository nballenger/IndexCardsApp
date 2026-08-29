from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QObject, Signal

from indexcards.models.card import MAX_TEXT_LENGTH, Card
from indexcards.models.link import Link
from indexcards.models.presets import PRESET_THEMES
from indexcards.models.stack import Stack
from indexcards.models.theme import Slot, Theme, clone_theme
from indexcards.utils.ids import new_theme_id

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
    stackAdded = Signal(str)
    stackRemoved = Signal(str)
    stackChanged = Signal(str, object)  # stack_id, frozenset[str] of changed fields
    stackMoved = Signal(str)
    stacksBulkMoved = Signal(object)  # list[str] of stack_ids
    dirtyChanged = Signal(bool)
    backgroundColorChanged = Signal(str)
    themeChanged = Signal()
    themeSlotChanged = Signal(str)

    def __init__(self, name: str = "Untitled", theme: Theme | None = None) -> None:
        super().__init__()
        self.name = name
        self.created_at = _now()
        self.modified_at = self.created_at
        self.cards: dict[str, Card] = {}
        self.links: dict[str, Link] = {}
        self.stacks: dict[str, Stack] = {}
        self.theme = theme if theme is not None else clone_theme(PRESET_THEMES[0])
        self._dirty = False

    # -- theme -------------------------------------------------------------

    @property
    def canvas_background_color(self) -> str:
        return self.theme.background_color

    @canvas_background_color.setter
    def canvas_background_color(self, color: str) -> None:
        self.theme.background_color = color

    def get_slot(self, slot_id: str) -> Slot:
        slot = self.theme.get_slot(slot_id)
        if slot is None:
            raise KeyError(f"no such slot: {slot_id}")
        return slot

    def set_theme_snapshot(self, theme: Theme) -> None:
        """Low-level whole-theme replacement — backs every operation that
        swaps self.theme wholesale (theme editing, switching themes, and
        undo/redo of both) via one shared command
        (commands/theme_commands.SetDocumentThemeCommand)."""
        if theme is self.theme:
            return
        self.theme = theme
        self._mark_dirty()
        self.themeChanged.emit()

    def plan_theme_edit(self, edited_theme: Theme) -> tuple[Theme, list[str]]:
        """Computes what should actually happen when the Theme Editor's
        proposed replacement for self.theme (edited_theme — same id, with
        slots possibly relabeled/recolored/reordered/removed) is applied.

        Does not mutate anything. Returns (theme_to_apply,
        newly_orphaned_slot_ids): any slot present in self.theme but
        missing from edited_theme is, if some card still references it,
        restored into theme_to_apply — with its *original* id/label/hex/
        text_color, overriding the editor's attempted deletion — flagged
        orphaned=True rather than actually removed. A slot the editor
        dropped that no card uses is genuinely gone.
        """
        old_slots_by_id = {slot.id: slot for slot in self.theme.slots}
        edited_ids = {slot.id for slot in edited_theme.slots}
        used_ids = {card.color_slot for card in self.cards.values()}

        theme_to_apply = clone_theme(edited_theme)
        newly_orphaned_slot_ids: list[str] = []
        for slot_id, old_slot in old_slots_by_id.items():
            if slot_id in edited_ids or slot_id not in used_ids:
                continue
            theme_to_apply.slots.append(
                Slot(
                    id=old_slot.id,
                    label=old_slot.label,
                    hex=old_slot.hex,
                    text_color=old_slot.text_color,
                    orphaned=True,
                )
            )
            newly_orphaned_slot_ids.append(slot_id)
        return theme_to_apply, newly_orphaned_slot_ids

    def plan_theme_switch(self, target_theme: Theme) -> tuple[Theme, list[str]]:
        """Computes what should actually happen when switching this
        document's active theme to target_theme (a preset or a different
        custom theme — never mutates target_theme itself).

        Does not mutate anything. Returns (theme_to_apply,
        newly_orphaned_slot_ids). If every slot currently in use is
        present and non-orphaned in target_theme, theme_to_apply is
        simply an independent clone of it (same id — so switching to a
        *duplicate* of the current theme is always orphan-free) and no
        card is touched. Otherwise theme_to_apply is a fresh custom-
        origin theme = target_theme's own slots plus the missing slots
        carried over from the *current* theme (original id/label/hex/
        text_color preserved, flagged orphaned=True) — so no card
        visibly changes color at the moment of the switch.
        """
        used_ids = {card.color_slot for card in self.cards.values()}
        target_active_ids = {slot.id for slot in target_theme.slots if not slot.orphaned}
        missing_ids = used_ids - target_active_ids

        if not missing_ids:
            return clone_theme(target_theme), []

        old_slots_by_id = {slot.id: slot for slot in self.theme.slots}
        target_all_ids = {slot.id for slot in target_theme.slots}
        carried = [
            Slot(
                id=old_slot.id,
                label=old_slot.label,
                hex=old_slot.hex,
                text_color=old_slot.text_color,
                orphaned=True,
            )
            for slot_id in missing_ids
            if slot_id not in target_all_ids and (old_slot := old_slots_by_id.get(slot_id))
        ]
        cloned = clone_theme(target_theme)
        theme_to_apply = Theme(
            id=new_theme_id(),
            name=cloned.name,
            origin="custom",
            background_color=cloned.background_color,
            slots=[*cloned.slots, *carried],
        )
        return theme_to_apply, [slot.id for slot in carried]

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
        text = text.strip()[:MAX_TEXT_LENGTH]
        card = self.cards[card_id]
        if card.text == text:
            return
        card.text = text
        card.modified_at = _now()
        self._mark_dirty()
        self.cardChanged.emit(card_id, frozenset({"text"}))

    def set_card_color_slot(self, card_id: str, slot_id: str) -> None:
        card = self.cards[card_id]
        if card.color_slot == slot_id:
            return
        card.color_slot = slot_id
        card.modified_at = _now()
        self._mark_dirty()
        self.cardChanged.emit(card_id, frozenset({"color_slot"}))

    def set_card_tags(self, card_id: str, tags: list[str]) -> None:
        card = self.cards[card_id]
        if card.tags == tags:
            return
        card.tags = list(tags)
        card.modified_at = _now()
        self._mark_dirty()
        self.cardChanged.emit(card_id, frozenset({"tags"}))

    def set_card_pinned(self, card_id: str, pinned: bool) -> None:
        card = self.cards[card_id]
        if card.pinned == pinned:
            return
        card.pinned = pinned
        card.modified_at = _now()
        self._mark_dirty()
        self.cardChanged.emit(card_id, frozenset({"pinned"}))

    def set_card_stack_id(self, card_id: str, stack_id: str | None) -> None:
        card = self.cards[card_id]
        if card.stack_id == stack_id:
            return
        card.stack_id = stack_id
        card.modified_at = _now()
        self._mark_dirty()
        self.cardChanged.emit(card_id, frozenset({"stack_id"}))

    def all_pinned(self, card_ids: list[str]) -> bool:
        """True if every card in card_ids is currently pinned (False for
        an empty list, matching Python's own all([]) convention would
        give True — but "are these cards pinned" for zero cards isn't a
        meaningful yes, so this is checked explicitly)."""
        return bool(card_ids) and all(self.cards[card_id].pinned for card_id in card_ids)

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

    # -- stacks --------------------------------------------------------------

    def get_stack(self, stack_id: str) -> Stack:
        return self.stacks[stack_id]

    def iter_stacks(self):
        return iter(self.stacks.values())

    def add_stack(self, stack: Stack, index: int | None = None) -> None:
        """Adds a stack, optionally re-inserting it at a specific position
        (see add_card's docstring for why: RemoveStackCommand.undo() needs
        to restore a stack to its original row rather than appending it)."""
        if stack.id in self.stacks:
            raise ValueError(f"stack id already exists: {stack.id}")
        if index is None or index >= len(self.stacks):
            self.stacks[stack.id] = stack
        else:
            items = list(self.stacks.items())
            items.insert(index, (stack.id, stack))
            self.stacks = dict(items)
        self._mark_dirty()
        self.stackAdded.emit(stack.id)

    def remove_stack(self, stack_id: str) -> Stack:
        """Removes a stack record only — does not touch member cards.
        Callers must have already cleared card.stack_id (Explode) or
        deleted the member cards outright (Delete Stack and Cards) before
        calling this, so no card is ever left pointing at a removed
        stack."""
        stack = self.stacks.pop(stack_id)
        self._mark_dirty()
        self.stackRemoved.emit(stack_id)
        return stack

    def set_stack_label(self, stack_id: str, label: str) -> None:
        label = label.strip()
        stack = self.stacks[stack_id]
        if stack.label == label:
            return
        stack.label = label
        stack.modified_at = _now()
        self._mark_dirty()
        self.stackChanged.emit(stack_id, frozenset({"label"}))

    def set_stack_position(self, stack_id: str, x: float, y: float) -> None:
        stack = self.stacks[stack_id]
        if stack.x == x and stack.y == y:
            return
        stack.x = x
        stack.y = y
        self._mark_dirty()
        self.stackMoved.emit(stack_id)

    def bulk_set_stack_positions(self, positions: dict[str, tuple[float, float]]) -> None:
        moved_ids = []
        for stack_id, (x, y) in positions.items():
            stack = self.stacks[stack_id]
            if stack.x == x and stack.y == y:
                continue
            stack.x = x
            stack.y = y
            moved_ids.append(stack_id)
        if not moved_ids:
            return
        self._mark_dirty()
        self.stacksBulkMoved.emit(moved_ids)

    def add_cards_to_stack(self, stack_id: str, card_ids: list[str]) -> None:
        """Adds each card to the stack: sets its stack_id, unpins it (a
        pinned card placed into a Stack becomes unpinned), and appends it
        to the stack's card_ids if not already present. Emits at most one
        stackChanged, only if the stack's membership actually grew."""
        stack = self.stacks[stack_id]
        added = False
        for card_id in card_ids:
            self.set_card_stack_id(card_id, stack_id)
            self.set_card_pinned(card_id, False)
            if card_id not in stack.card_ids:
                stack.card_ids.append(card_id)
                added = True
        if added:
            stack.modified_at = _now()
            self._mark_dirty()
            self.stackChanged.emit(stack_id, frozenset({"card_ids"}))

    def remove_cards_from_stack(self, stack_id: str, card_ids: list[str]) -> None:
        """Inverse of add_cards_to_stack: clears stack_id on each card
        still present (a card may already have been deleted outright, e.g.
        mid Delete-Stack-and-Cards) and drops it from the stack's
        card_ids. Emits at most one stackChanged, only if membership
        actually shrank."""
        stack = self.stacks[stack_id]
        removed = False
        for card_id in card_ids:
            card = self.cards.get(card_id)
            if card is not None:
                self.set_card_stack_id(card_id, None)
            if card_id in stack.card_ids:
                stack.card_ids.remove(card_id)
                removed = True
        if removed:
            stack.modified_at = _now()
            self._mark_dirty()
            self.stackChanged.emit(stack_id, frozenset({"card_ids"}))

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

    def connected_card_ids(self, card_id: str) -> set[str]:
        """Every card reachable from card_id by walking the link graph any
        number of hops — its full connected component, including card_id
        itself. Assumes card_id references an existing card."""
        adjacency: dict[str, set[str]] = {}
        for link in self.links.values():
            adjacency.setdefault(link.source, set()).add(link.target)
            adjacency.setdefault(link.target, set()).add(link.source)
        visited = {card_id}
        frontier = [card_id]
        while frontier:
            current = frontier.pop()
            for neighbor in adjacency.get(current, ()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    frontier.append(neighbor)
        return visited
