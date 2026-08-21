from __future__ import annotations

from PySide6.QtGui import QUndoCommand

from indexcards.models.document import Document
from indexcards.models.link import Link


class AddLinkCommand(QUndoCommand):
    def __init__(self, document: Document, link: Link) -> None:
        super().__init__("Add Link")
        self._document = document
        self._link = link

    def redo(self) -> None:
        self._document.add_link(self._link)

    def undo(self) -> None:
        self._document.remove_link(self._link.id)


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
