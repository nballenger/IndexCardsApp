from __future__ import annotations

from PySide6.QtGui import QUndoCommand

from indexcards.models.document import Document
from indexcards.models.link import Link


class AddLinkCommand(QUndoCommand):
    """Adds a link and pins both endpoint cards — linking implies a desire
    to relate them spatially. Restores each card's own prior pinned state
    on undo (mirrors CreateStackCommand's _old_pinned bookkeeping), so a
    card that was already pinned by another link stays pinned rather than
    being unpinned just because this particular link is undone."""

    def __init__(self, document: Document, link: Link) -> None:
        super().__init__("Add Link")
        self._document = document
        self._link = link
        self._old_pinned = {
            link.source: document.get_card(link.source).pinned,
            link.target: document.get_card(link.target).pinned,
        }

    def redo(self) -> None:
        self._document.add_link(self._link)
        self._document.set_card_pinned(self._link.source, True)
        self._document.set_card_pinned(self._link.target, True)

    def undo(self) -> None:
        self._document.remove_link(self._link.id)
        for card_id, pinned in self._old_pinned.items():
            self._document.set_card_pinned(card_id, pinned)


class DeleteLinkCommand(QUndoCommand):
    def __init__(self, document: Document, link_id: str) -> None:
        super().__init__("Delete Link")
        self._document = document
        self._link_id = link_id
        self._removed_link: Link | None = None

    def redo(self) -> None:
        self._removed_link = self._document.remove_link(self._link_id)

    def undo(self) -> None:
        self._document.add_link(self._removed_link)


class ChangeLinkLineEndingsCommand(QUndoCommand):
    """Sets line_ending on every link in link_ids as one undo step,
    restoring each link's own prior value individually on undo (a mixed
    multi-selection's "before" isn't uniform) — mirrors TogglePinCommand
    (commands/card_commands.py)."""

    def __init__(self, document: Document, link_ids: list[str], line_ending: str) -> None:
        super().__init__("Change Line Endings")
        self._document = document
        self._link_ids = list(link_ids)
        self._line_ending = line_ending
        self._old_endings = {
            link_id: document.get_link(link_id).line_ending for link_id in self._link_ids
        }

    def redo(self) -> None:
        for link_id in self._link_ids:
            self._document.set_link_line_ending(link_id, self._line_ending)

    def undo(self) -> None:
        for link_id, old_ending in self._old_endings.items():
            self._document.set_link_line_ending(link_id, old_ending)
