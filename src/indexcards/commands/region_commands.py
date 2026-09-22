from __future__ import annotations

from PySide6.QtGui import QUndoCommand, QUndoStack

from indexcards.models.document import Document
from indexcards.models.region import Region


class AddRegionCommand(QUndoCommand):
    def __init__(self, document: Document, region: Region) -> None:
        super().__init__("Add Region")
        self._document = document
        self._region = region

    def redo(self) -> None:
        self._document.add_region(self._region)

    def undo(self) -> None:
        self._document.remove_region(self._region.id)


class RemoveRegionCommand(QUndoCommand):
    """Removes a region record only -- membership is derived from position,
    so no card or stack needs updating. Mirrors RemoveStackCommand's
    index-preserving restore on undo."""

    def __init__(self, document: Document, region_id: str) -> None:
        super().__init__("Delete Region")
        self._document = document
        self._region_id = region_id
        self._region_index = 0
        self._removed_region: Region | None = None

    def redo(self) -> None:
        self._region_index = list(self._document.regions.keys()).index(self._region_id)
        self._removed_region = self._document.remove_region(self._region_id)

    def undo(self) -> None:
        self._document.add_region(self._removed_region, index=self._region_index)


class ChangeRegionLabelCommand(QUndoCommand):
    def __init__(self, document: Document, region_id: str, old_label: str, new_label: str) -> None:
        super().__init__("Label Region")
        self._document = document
        self._region_id = region_id
        self._old_label = old_label
        self._new_label = new_label

    def redo(self) -> None:
        self._document.set_region_label(self._region_id, self._new_label)

    def undo(self) -> None:
        self._document.set_region_label(self._region_id, self._old_label)


class ResizeRegionCommand(QUndoCommand):
    """old/new_geometry are (x, y, width, height) tuples. Resizing never
    moves cards in stage 1 -- membership can change as a side effect of the
    new rectangle, but that's a read, not a write."""

    def __init__(
        self,
        document: Document,
        region_id: str,
        old_geometry: tuple[float, float, float, float],
        new_geometry: tuple[float, float, float, float],
    ) -> None:
        super().__init__("Resize Region")
        self._document = document
        self._region_id = region_id
        self._old_geometry = old_geometry
        self._new_geometry = new_geometry

    def redo(self) -> None:
        self._document.set_region_geometry(self._region_id, *self._new_geometry)

    def undo(self) -> None:
        self._document.set_region_geometry(self._region_id, *self._old_geometry)


class MoveRegionCommand(QUndoCommand):
    """Moves a region and carries the cards/stacks that were inside it at
    drag start, as one undo step. old/new_position are (x, y) for the
    region itself; old/new_card_positions and old/new_stack_positions are
    {id: (x, y)} for whatever traveled with it (captured by the caller from
    regions.geometry.contained_card_ids/contained_stack_ids at press time)."""

    def __init__(
        self,
        document: Document,
        region_id: str,
        old_position: tuple[float, float],
        new_position: tuple[float, float],
        old_card_positions: dict[str, tuple[float, float]],
        new_card_positions: dict[str, tuple[float, float]],
        old_stack_positions: dict[str, tuple[float, float]],
        new_stack_positions: dict[str, tuple[float, float]],
    ) -> None:
        super().__init__("Move Region")
        self._document = document
        self._region_id = region_id
        self._old_position = old_position
        self._new_position = new_position
        self._old_card_positions = dict(old_card_positions)
        self._new_card_positions = dict(new_card_positions)
        self._old_stack_positions = dict(old_stack_positions)
        self._new_stack_positions = dict(new_stack_positions)

    def _region_geometry(self, x: float, y: float) -> tuple[float, float, float, float]:
        region = self._document.get_region(self._region_id)
        return (x, y, region.width, region.height)

    def redo(self) -> None:
        self._document.set_region_geometry(
            self._region_id, *self._region_geometry(*self._new_position)
        )
        if self._new_card_positions:
            self._document.bulk_set_positions(self._new_card_positions)
        if self._new_stack_positions:
            self._document.bulk_set_stack_positions(self._new_stack_positions)

    def undo(self) -> None:
        self._document.set_region_geometry(
            self._region_id, *self._region_geometry(*self._old_position)
        )
        if self._old_card_positions:
            self._document.bulk_set_positions(self._old_card_positions)
        if self._old_stack_positions:
            self._document.bulk_set_stack_positions(self._old_stack_positions)


def push_region_growth_result(
    undo_stack: QUndoStack,
    document: Document,
    primary_command: QUndoCommand,
    other_diffs: dict[str, tuple[float, float, float, float]],
) -> None:
    """Pushes primary_command (the Add/Move/Resize for the region a gesture
    actually touched) plus one ResizeRegionCommand per OTHER region that
    regions.growth.resolve_region_growth() found had to grow, as a single
    undo step whenever there's more than one push.

    A plain helper, not a QUndoCommand subclass, so it composes with
    whichever command the caller already built for its own gesture rather
    than duplicating that logic (mirrors stack_commands.py's
    push_delete_stack_and_cards). QUndoStack doesn't support nested
    macros -- a caller that needs to combine this with pushes of its own
    must inline it inside its own beginMacro/endMacro instead of calling
    this as a black box.
    """
    if not other_diffs:
        undo_stack.push(primary_command)
        return
    undo_stack.beginMacro(primary_command.text())
    undo_stack.push(primary_command)
    for region_id, new_geometry in other_diffs.items():
        region = document.get_region(region_id)
        old_geometry = (region.x, region.y, region.width, region.height)
        undo_stack.push(ResizeRegionCommand(document, region_id, old_geometry, new_geometry))
    undo_stack.endMacro()
