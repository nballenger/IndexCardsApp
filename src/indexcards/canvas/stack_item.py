from __future__ import annotations

import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QAction,
    QColor,
    QFontMetrics,
    QPainter,
    QPen,
    QPolygonF,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsSceneContextMenuEvent,
    QGraphicsSceneMouseEvent,
    QInputDialog,
    QMenu,
    QStyleOptionGraphicsItem,
    QWidget,
)

from indexcards.arrange.stack_arrange import compute_explode_layout
from indexcards.commands.move_commands import MoveStackCommand
from indexcards.commands.stack_commands import (
    ChangeStackLabelCommand,
    ExplodeStackCommand,
    push_delete_stack_and_cards,
)
from indexcards.models.card import DEFAULT_CARD_SIZE
from indexcards.models.document import Document
from indexcards.widgets.stack_dialogs import confirm_delete_stack

_STACK_DEPTH = 20.0  # ~1/10 of a card's width (200) — the box's apparent thickness
_LINE_COUNT = 5  # number of thin card-edge indicator lines drawn per face
_BADGE_MARGIN = 6.0
_BADGE_HEIGHT = 18.0
_BADGE_MIN_WIDTH = 22.0
_BADGE_PADDING = 6.0
_LABEL_MARGIN = 8.0

_TOP_FILL = QColor("#FFFFFF")
_FRONT_FILL = QColor("#EDEDED")
_RIGHT_FILL = QColor("#DADADA")
_EDGE_LINE_COLOR = QColor(140, 140, 140)


class StackItem(QGraphicsObject):
    """Renders one Stack as an isometric-looking box at its stored
    position: a card-sized top face (always white, regardless of member
    card colors) plus a thin extruded front/right face suggesting a
    stack of cards, a card-count badge, and an optional label.

    Selectable and draggable exactly like CardItem (ItemIsMovable +
    mouseReleaseEvent pushing a MoveStackCommand), and — per spec — never
    touched by auto-arrange.
    """

    def __init__(
        self,
        stack_id: str,
        document: Document,
        undo_stack: QUndoStack | None = None,
        parent: QGraphicsItem | None = None,
    ) -> None:
        super().__init__(parent)
        self.stack_id = stack_id
        self._document = document
        self._undo_stack = undo_stack
        self._press_pos: tuple[float, float] | None = None

        flags = QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        if undo_stack is not None:
            flags |= QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        self.setFlags(flags)

    def boundingRect(self) -> QRectF:
        width, height = DEFAULT_CARD_SIZE
        return QRectF(0, 0, width + _STACK_DEPTH, height + _STACK_DEPTH)

    def _faces(self) -> tuple[QRectF, QPolygonF, QPolygonF]:
        width, height = DEFAULT_CARD_SIZE
        d = _STACK_DEPTH
        top = QRectF(0, 0, width, height)
        right = QPolygonF(
            [
                QPointF(width, 0),
                QPointF(width + d, d),
                QPointF(width + d, height + d),
                QPointF(width, height),
            ]
        )
        front = QPolygonF(
            [
                QPointF(0, height),
                QPointF(d, height + d),
                QPointF(width + d, height + d),
                QPointF(width, height),
            ]
        )
        return top, right, front

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        stack = self._document.get_stack(self.stack_id)
        top, right, front = self._faces()

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen_width = 2 if self.isSelected() else 1
        pen_color = Qt.GlobalColor.black if self.isSelected() else Qt.GlobalColor.darkGray
        outline = QPen(pen_color, pen_width)

        painter.setPen(outline)
        painter.setBrush(_RIGHT_FILL)
        painter.drawPolygon(right)
        painter.setBrush(_FRONT_FILL)
        painter.drawPolygon(front)
        painter.setBrush(_TOP_FILL)
        painter.drawRect(top)

        self._paint_front_face_lines(painter, front)
        self._paint_right_face_lines(painter, right)
        painter.restore()

        self._paint_badge(painter, top, len(stack.card_ids))
        if stack.label:
            self._paint_label(painter, top, stack.label)

    def _paint_front_face_lines(self, painter: QPainter, front: QPolygonF) -> None:
        """Thin horizontal lines suggesting stacked card edges across the
        front face. front's top edge (at(0)-at(3)) and bottom edge
        (at(1)-at(2)) are themselves already exactly horizontal (both
        endpoints of each share a y value), so lerping between the two
        edges at the same fraction naturally produces horizontal lines."""
        top_left, bottom_left, bottom_right, top_right = (
            front.at(0),
            front.at(1),
            front.at(2),
            front.at(3),
        )
        painter.save()
        painter.setPen(QPen(_EDGE_LINE_COLOR, 1))
        for i in range(1, _LINE_COUNT):
            t = i / _LINE_COUNT
            start = top_left + (bottom_left - top_left) * t
            end = top_right + (bottom_right - top_right) * t
            painter.drawLine(start, end)
        painter.restore()

    def _paint_right_face_lines(self, painter: QPainter, right: QPolygonF) -> None:
        """Thin horizontal lines across the right face. Unlike the front
        face, the right face's parallel edges (top/bottom) are diagonal,
        not horizontal — so rather than lerping between them (which would
        yield vertical lines), this draws literal horizontal chords
        spanning the face's near (x=w) to far (x=w+depth) edges, sampled
        within the vertical range common to both of those edges (depth to
        card_height - depth) so every chord stays inside the polygon."""
        _width, height = DEFAULT_CARD_SIZE
        x_near = right.at(0).x()
        x_far = right.at(1).x()
        y_min, y_max = _STACK_DEPTH, height - _STACK_DEPTH
        painter.save()
        painter.setPen(QPen(_EDGE_LINE_COLOR, 1))
        for i in range(1, _LINE_COUNT):
            t = i / _LINE_COUNT
            y = y_min + (y_max - y_min) * t
            painter.drawLine(QPointF(x_near, y), QPointF(x_far, y))
        painter.restore()

    def _paint_badge(self, painter: QPainter, top: QRectF, count: int) -> None:
        text = str(count)
        metrics = QFontMetrics(painter.font())
        text_width = metrics.horizontalAdvance(text)
        badge_width = max(_BADGE_MIN_WIDTH, text_width + 2 * _BADGE_PADDING)
        badge_rect = QRectF(
            top.right() - _BADGE_MARGIN - badge_width,
            top.top() + _BADGE_MARGIN,
            badge_width,
            _BADGE_HEIGHT,
        )

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(90, 90, 90))
        painter.setPen(Qt.PenStyle.NoPen)
        radius = badge_rect.height() / 2
        painter.drawRoundedRect(badge_rect, radius, radius)
        painter.setPen(QColor(Qt.GlobalColor.white))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()

    def _paint_label(self, painter: QPainter, top: QRectF, label: str) -> None:
        metrics = QFontMetrics(painter.font())
        available_width = top.width() - 2 * _LABEL_MARGIN
        elided = metrics.elidedText(label, Qt.TextElideMode.ElideRight, int(available_width))

        painter.save()
        painter.setPen(QColor(Qt.GlobalColor.black))
        text_rect = top.adjusted(_LABEL_MARGIN, 0, -_LABEL_MARGIN, 0)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, elided)
        painter.restore()

    def refresh(self) -> None:
        self.update()

    # -- drag ---------------------------------------------------------------

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
            self._undo_stack.push(MoveStackCommand(self._document, self.stack_id, old_pos, new_pos))

    # -- context menu ---------------------------------------------------------

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:
        if self._undo_stack is None:
            event.ignore()
            return
        menu, delete_action, tile_action, scatter_action, label_action = self._build_context_menu()
        chosen = menu.exec(event.screenPos())
        if chosen is delete_action:
            self._delete_via_dialog()
        elif chosen is tile_action:
            self._explode("tile")
        elif chosen is scatter_action:
            self._explode("scatter")
        elif chosen is label_action:
            self._edit_label_via_dialog()

    def _build_context_menu(self) -> tuple[QMenu, QAction, QAction, QAction, QAction]:
        """Builds the menu without exec()'ing it, so tests can inspect its
        contents without triggering a real, blocking modal popup."""
        stack = self._document.get_stack(self.stack_id)

        menu = QMenu()
        delete_action = menu.addAction("Delete")
        menu.addSeparator()
        tile_action = menu.addAction("Explode and Tile")
        scatter_action = menu.addAction("Explode and Scatter")
        menu.addSeparator()
        label_action = menu.addAction("Change Label" if stack.label else "Label")

        return menu, delete_action, tile_action, scatter_action, label_action

    def _delete_via_dialog(self) -> None:
        stack = self._document.get_stack(self.stack_id)
        parent_widget = self.scene().views()[0] if self.scene() and self.scene().views() else None
        if not confirm_delete_stack(parent_widget, stack.label, len(stack.card_ids)):
            return
        push_delete_stack_and_cards(self._undo_stack, self._document, self.stack_id)

    def _explode(self, group_by: str) -> None:
        scene = self.scene()
        if scene is None or not scene.views():
            return
        view = scene.views()[0]

        stack = self._document.get_stack(self.stack_id)
        member_ids = list(stack.card_ids)
        member_cards = [self._document.get_card(card_id) for card_id in member_ids]
        other_card_positions = {
            card.id: (card.x, card.y)
            for card in self._document.iter_cards()
            if card.stack_id is None
        }
        other_stack_positions = {
            other.id: (other.x, other.y)
            for other in self._document.iter_stacks()
            if other.id != self.stack_id
        }
        viewport_size = view.viewport().size()
        aspect_ratio = (
            viewport_size.width() / viewport_size.height() if viewport_size.height() else 1.0
        )
        new_positions = compute_explode_layout(
            stack,
            member_cards,
            group_by,
            other_card_positions,
            other_stack_positions,
            aspect_ratio=aspect_ratio,
            rng=random.Random(),
        )
        self._undo_stack.push(ExplodeStackCommand(self._document, self.stack_id, new_positions))
        view.fit_to_positions(new_positions)

    def _edit_label_via_dialog(self) -> None:
        stack = self._document.get_stack(self.stack_id)
        parent_widget = self.scene().views()[0] if self.scene() and self.scene().views() else None
        text, ok = QInputDialog.getText(
            parent_widget, "Label Stack", "Label:", text=stack.label
        )
        if not ok:
            return
        new_label = text.strip()
        if new_label == stack.label:
            return
        self._undo_stack.push(
            ChangeStackLabelCommand(self._document, self.stack_id, stack.label, new_label)
        )
