from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QTextDocument, QUndoStack
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsSceneMouseEvent,
    QStyleOptionGraphicsItem,
    QWidget,
)

from indexcards.commands.move_commands import MoveCardCommand
from indexcards.models.card import DEFAULT_CARD_SIZE
from indexcards.models.document import Document

_TEXT_MARGIN = 8
_CORNER_RADIUS = 8


class CardItem(QGraphicsObject):
    """Renders one Card at its stored position.

    Draggable only when constructed with an undo_stack: mouseReleaseEvent
    pushes a MoveCardCommand rather than leaving the moved position as
    view-only state, so a drag on the canvas persists and undoes the same
    way a list-view edit does.
    """

    def __init__(
        self,
        card_id: str,
        document: Document,
        undo_stack: QUndoStack | None = None,
        parent: QGraphicsItem | None = None,
    ) -> None:
        super().__init__(parent)
        self.card_id = card_id
        self._document = document
        self._undo_stack = undo_stack
        self._press_pos: tuple[float, float] | None = None

        flags = QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        if undo_stack is not None:
            flags |= QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            flags |= QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        self.setFlags(flags)

        self._text_doc = QTextDocument()
        self._sync_text_doc()

    def boundingRect(self) -> QRectF:
        width, height = DEFAULT_CARD_SIZE
        return QRectF(0, 0, width, height)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        card = self._document.get_card(self.card_id)
        rect = self.boundingRect()

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(card.color))
        pen_width = 2 if self.isSelected() else 1
        pen_color = Qt.GlobalColor.black if self.isSelected() else Qt.GlobalColor.darkGray
        painter.setPen(QPen(pen_color, pen_width))
        painter.drawRoundedRect(rect, _CORNER_RADIUS, _CORNER_RADIUS)
        painter.restore()

        text_rect = rect.adjusted(_TEXT_MARGIN, _TEXT_MARGIN, -_TEXT_MARGIN, -_TEXT_MARGIN)
        painter.save()
        painter.translate(text_rect.topLeft())
        self._text_doc.setTextWidth(text_rect.width())
        clip = QRectF(0, 0, text_rect.width(), text_rect.height())
        painter.setClipRect(clip)
        self._text_doc.drawContents(painter, clip)
        painter.restore()

    def refresh(self) -> None:
        self._sync_text_doc()
        self.update()

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._undo_stack is not None:
            self._press_pos = (self.pos().x(), self.pos().y())
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        if self._undo_stack is None or self._press_pos is None:
            return
        old_pos = self._press_pos
        self._press_pos = None
        new_pos = (self.pos().x(), self.pos().y())
        if new_pos != old_pos:
            self._undo_stack.push(MoveCardCommand(self._document, self.card_id, old_pos, new_pos))

    def _sync_text_doc(self) -> None:
        card = self._document.get_card(self.card_id)
        self._text_doc.setMarkdown(card.text)
