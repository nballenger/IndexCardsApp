from __future__ import annotations

from PySide6.QtGui import QUndoCommand

from indexcards.models.document import Document
from indexcards.models.theme import Slot, Theme


class SetDocumentThemeCommand(QUndoCommand):
    """Backs every whole-theme replacement: committing Theme Editor edits,
    switching to a different theme, and undo/redo of both — a single
    shared command rather than one per trigger, since they're all "swap
    self.theme wholesale" at the model level.

    color_slot_remap (old slot id -> new slot id) is only ever non-empty
    for a theme *switch* that carried some slots across positionally
    (see Document.plan_theme_switch) — editing the current theme never
    needs it, since kept slots keep their own id. redo applies it
    forward; undo applies its exact reverse, so a card that moved from
    slot A to slot B on redo moves back from B to A on undo regardless
    of anything else that happened to the document in between."""

    def __init__(
        self,
        document: Document,
        old_theme: Theme,
        new_theme: Theme,
        color_slot_remap: dict[str, str] | None = None,
    ) -> None:
        super().__init__("Change Theme")
        self._document = document
        self._old_theme = old_theme
        self._new_theme = new_theme
        self._remap = dict(color_slot_remap) if color_slot_remap else {}
        self._reverse_remap = {new_id: old_id for old_id, new_id in self._remap.items()}

    def redo(self) -> None:
        self._document.apply_theme_switch(self._new_theme, self._remap)

    def undo(self) -> None:
        self._document.apply_theme_switch(self._old_theme, self._reverse_remap)


class KeepOrphanColorCommand(QUndoCommand):
    """'Keep as a permanent theme color' — clears the orphaned flag in
    place. No card is touched."""

    def __init__(self, document: Document, slot_id: str) -> None:
        super().__init__("Keep Orphaned Color")
        self._document = document
        self._slot_id = slot_id

    def redo(self) -> None:
        self._document.clear_slot_orphaned(self._slot_id)

    def undo(self) -> None:
        self._document.set_slot_orphaned(self._slot_id, True)


class ReassignOrphanColorCommand(QUndoCommand):
    """Rewrites every card on the orphan slot to a target slot, then
    removes the now-unreferenced orphan slot from the theme. Captures
    what redo() actually did (which cards moved, the slot's original
    index) before mutating, mirroring DeleteCardCommand's pattern, so
    undo is exact regardless of what else changed in between pushes."""

    def __init__(self, document: Document, orphan_slot_id: str, target_slot_id: str) -> None:
        super().__init__("Reassign Orphaned Color")
        self._document = document
        self._orphan_slot_id = orphan_slot_id
        self._target_slot_id = target_slot_id
        self._removed_slot: Slot | None = None
        self._removed_index: int | None = None
        self._old_card_slots: dict[str, str] = {}

    def redo(self) -> None:
        self._removed_index = next(
            i
            for i, slot in enumerate(self._document.theme.slots)
            if slot.id == self._orphan_slot_id
        )
        self._removed_slot = self._document.get_slot(self._orphan_slot_id)
        self._old_card_slots = {
            card.id: card.color_slot
            for card in self._document.cards.values()
            if card.color_slot == self._orphan_slot_id
        }
        self._document.reassign_orphan_slot(self._orphan_slot_id, self._target_slot_id)

    def undo(self) -> None:
        self._document.restore_theme_slot(self._removed_slot, self._removed_index)
        for card_id, old_slot_id in self._old_card_slots.items():
            self._document.set_card_color_slot(card_id, old_slot_id)
