from __future__ import annotations

from PySide6.QtGui import QUndoCommand, QUndoStack

from indexcards.commands.card_commands import DeleteCardCommand
from indexcards.models.document import Document
from indexcards.models.stack import Stack


class CreateStackCommand(QUndoCommand):
    """Creates a new stack containing card_ids (which must not already
    belong to any stack). Restores each card's own pinned state on undo,
    since joining a stack unpins it as a side effect."""

    def __init__(self, document: Document, stack: Stack, card_ids: list[str]) -> None:
        super().__init__("Create Stack")
        self._document = document
        self._stack = stack
        self._card_ids = list(card_ids)
        self._old_pinned = {
            card_id: document.get_card(card_id).pinned for card_id in self._card_ids
        }

    def redo(self) -> None:
        self._document.add_stack(self._stack)
        self._document.add_cards_to_stack(self._stack.id, self._card_ids)

    def undo(self) -> None:
        self._document.remove_cards_from_stack(self._stack.id, self._card_ids)
        for card_id, pinned in self._old_pinned.items():
            self._document.set_card_pinned(card_id, pinned)
        self._document.remove_stack(self._stack.id)


class AddCardsToStackCommand(QUndoCommand):
    """Adds card_ids to an already-existing stack. Restores each card's own
    pinned state on undo, same reasoning as CreateStackCommand."""

    def __init__(self, document: Document, stack_id: str, card_ids: list[str]) -> None:
        super().__init__("Add to Stack")
        self._document = document
        self._stack_id = stack_id
        self._card_ids = list(card_ids)
        self._old_pinned = {
            card_id: document.get_card(card_id).pinned for card_id in self._card_ids
        }

    def redo(self) -> None:
        self._document.add_cards_to_stack(self._stack_id, self._card_ids)

    def undo(self) -> None:
        self._document.remove_cards_from_stack(self._stack_id, self._card_ids)
        for card_id, pinned in self._old_pinned.items():
            self._document.set_card_pinned(card_id, pinned)


class RemoveCardFromStackCommand(QUndoCommand):
    """Removes one card from a stack and places it at new_position on the
    canvas — pushed (via push_eject_card_from_stack) when a tile is
    dragged out of the stack-contents overlay. Does not touch the Stack
    record itself — a caller ejecting a stack down to 0-1 remaining
    members must separately push RemoveStackCommand once every member's
    stack_id has already been cleared."""

    def __init__(
        self, document: Document, stack_id: str, card_id: str, new_position: tuple[float, float]
    ) -> None:
        super().__init__("Remove from Stack")
        self._document = document
        self._stack_id = stack_id
        self._card_id = card_id
        self._new_position = new_position
        card = document.get_card(card_id)
        self._old_position = (card.x, card.y)
        self._old_index = document.get_stack(stack_id).card_ids.index(card_id)

    def redo(self) -> None:
        self._document.remove_cards_from_stack(self._stack_id, [self._card_id])
        self._document.bulk_set_positions({self._card_id: self._new_position})

    def undo(self) -> None:
        self._document.bulk_set_positions({self._card_id: self._old_position})
        self._document.restore_card_to_stack(self._stack_id, self._card_id, self._old_index)


class RemoveStackCommand(QUndoCommand):
    """Removes a stack record only — assumes the caller has already dealt
    with member cards (cleared their stack_id, or deleted them outright).
    Mirrors DeleteCardCommand's index-preserving restore on undo."""

    def __init__(self, document: Document, stack_id: str) -> None:
        super().__init__("Remove Stack")
        self._document = document
        self._stack_id = stack_id
        self._stack_index = 0
        self._removed_stack: Stack | None = None

    def redo(self) -> None:
        self._stack_index = list(self._document.stacks.keys()).index(self._stack_id)
        self._removed_stack = self._document.remove_stack(self._stack_id)

    def undo(self) -> None:
        self._document.add_stack(self._removed_stack, index=self._stack_index)


class ExplodeStackCommand(QUndoCommand):
    """Un-tracks a stack and scatters/tiles its member cards to
    new_positions, as one atomic undo step: clears every member's
    stack_id, repositions them, then removes the stack record.

    remove_cards_from_stack() mutates stack.card_ids in place, and
    remove_stack() then returns that same (now-emptied) Stack object — so
    undo() must restore self._removed_stack.card_ids from the separately
    held self._card_ids snapshot before re-adding it, or the restored
    stack would come back with an empty (badge-0) member list.
    """

    def __init__(
        self,
        document: Document,
        stack_id: str,
        new_positions: dict[str, tuple[float, float]],
    ) -> None:
        super().__init__("Explode Stack")
        self._document = document
        self._stack_id = stack_id
        self._card_ids = list(document.get_stack(stack_id).card_ids)
        self._old_positions = {
            card_id: (document.get_card(card_id).x, document.get_card(card_id).y)
            for card_id in self._card_ids
        }
        self._new_positions = dict(new_positions)
        self._stack_index = 0
        self._removed_stack: Stack | None = None

    def redo(self) -> None:
        self._document.remove_cards_from_stack(self._stack_id, self._card_ids)
        self._document.bulk_set_positions(self._new_positions)
        self._stack_index = list(self._document.stacks.keys()).index(self._stack_id)
        self._removed_stack = self._document.remove_stack(self._stack_id)

    def undo(self) -> None:
        self._removed_stack.card_ids = list(self._card_ids)
        self._document.add_stack(self._removed_stack, index=self._stack_index)
        self._document.bulk_set_positions(self._old_positions)
        for card_id in self._card_ids:
            self._document.set_card_stack_id(card_id, self._stack_id)


class ChangeStackLabelCommand(QUndoCommand):
    def __init__(self, document: Document, stack_id: str, old_label: str, new_label: str) -> None:
        super().__init__("Change Stack Label")
        self._document = document
        self._stack_id = stack_id
        self._old_label = old_label
        self._new_label = new_label

    def redo(self) -> None:
        self._document.set_stack_label(self._stack_id, self._new_label)

    def undo(self) -> None:
        self._document.set_stack_label(self._stack_id, self._old_label)


class ReorderStackCommand(QUndoCommand):
    """Reorders a stack's card_ids — pushed by StackOverlay after a
    drag-to-reorder inside the stack-contents overlay ends with a
    different order than it started."""

    def __init__(
        self, document: Document, stack_id: str, old_order: list[str], new_order: list[str]
    ) -> None:
        super().__init__("Reorder Stack")
        self._document = document
        self._stack_id = stack_id
        self._old_order = list(old_order)
        self._new_order = list(new_order)

    def redo(self) -> None:
        self._document.set_stack_card_order(self._stack_id, self._new_order)

    def undo(self) -> None:
        self._document.set_stack_card_order(self._stack_id, self._old_order)


class GatherStacksCommand(QUndoCommand):
    """Repositions many stacks atomically — one undo step for the whole
    Gather Stacks run, mirroring AutoArrangeCommand for cards."""

    def __init__(
        self,
        document: Document,
        old_positions: dict[str, tuple[float, float]],
        new_positions: dict[str, tuple[float, float]],
    ) -> None:
        super().__init__("Gather Stacks")
        self._document = document
        self._old_positions = old_positions
        self._new_positions = new_positions

    def redo(self) -> None:
        self._document.bulk_set_stack_positions(self._new_positions)

    def undo(self) -> None:
        self._document.bulk_set_stack_positions(self._old_positions)


def push_delete_stack_and_cards(undo_stack: QUndoStack, document: Document, stack_id: str) -> None:
    """Deletes a stack and every one of its member cards (cascading their
    own incident links too, via DeleteCardCommand) as one undo step.

    A plain helper, not a QUndoCommand subclass, so it composes with
    existing atomic commands (reusing DeleteCardCommand's link-cascade
    behavior for free) rather than duplicating that logic. QUndoStack
    doesn't support nested macros — a caller that wants to wrap several
    stacks' deletion in one single outer undo step must inline this
    function's pushes directly inside its own beginMacro/endMacro instead
    of calling this helper as a black box.
    """
    stack = document.get_stack(stack_id)
    member_ids = list(stack.card_ids)
    undo_stack.beginMacro(f"Delete Stack and {len(member_ids)} Card(s)")
    for card_id in member_ids:
        undo_stack.push(DeleteCardCommand(document, card_id))
    undo_stack.push(RemoveStackCommand(document, stack_id))
    undo_stack.endMacro()


def push_eject_card_from_stack(
    undo_stack: QUndoStack,
    document: Document,
    stack_id: str,
    card_id: str,
    new_position: tuple[float, float],
) -> None:
    """Ejects one card from a stack onto the canvas, as one undo step. If
    this leaves the stack with 1 or fewer members, the whole stack
    auto-dissolves as part of the same step: any remaining member is
    freed too (staying at its current position) and the Stack record
    itself is removed — mirroring ExplodeStackCommand's reasoning that a
    "stack" of 0-1 cards is never a meaningful state."""
    stack = document.get_stack(stack_id)
    remaining_ids = [cid for cid in stack.card_ids if cid != card_id]
    undo_stack.beginMacro("Remove from Stack")
    undo_stack.push(RemoveCardFromStackCommand(document, stack_id, card_id, new_position))
    if len(remaining_ids) <= 1:
        for last_id in remaining_ids:
            last_card = document.get_card(last_id)
            undo_stack.push(
                RemoveCardFromStackCommand(document, stack_id, last_id, (last_card.x, last_card.y))
            )
        undo_stack.push(RemoveStackCommand(document, stack_id))
    undo_stack.endMacro()
