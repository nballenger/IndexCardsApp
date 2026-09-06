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
    QDialog,
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
from indexcards.canvas.drop_highlight import apply_drop_highlight
from indexcards.commands.move_commands import MoveStackCommand
from indexcards.commands.stack_commands import (
    ChangeStackLabelCommand,
    ExplodeStackCommand,
    MergeStacksCommand,
    push_delete_stack_and_cards,
)
from indexcards.models.card import DEFAULT_CARD_SIZE
from indexcards.models.document import Document
from indexcards.models.stack import Stack
from indexcards.utils.contrast import auto_text_color, selection_outline_color
from indexcards.utils.ids import new_stack_id
from indexcards.widgets.stack_dialogs import CreateStackPromptDialog, confirm_delete_stack

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

_BADGE_COLOR = QColor(90, 90, 90)
_BADGE_MATCH_COLOR = QColor(200, 40, 40)  # a selected member matched the search
# The box faces are already near-white/gray, so desaturating them further
# (CardItem's own technique) would be a visual no-op — reduced opacity on
# the whole item reads as "de-emphasized" instead, same as it would for a
# solid-colored item with nothing worth showing through it.
_DIMMED_OPACITY = 0.35


class StackItem(QGraphicsObject):
    """Renders one Stack as an isometric-looking box at its stored
    position: a card-sized top face showing the top (most recently
    added) member's color, plus a thin extruded front/right face banded
    one stripe per member card in stack order -- mirroring the way a
    real stack of colored paper shows its composition as edge-striping
    -- a card-count badge, and an optional label. An empty stack (no
    members) falls back to a plain white/gray box.

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
        self._drop_highlight_target: StackItem | None = None
        # None = no active search (default rendering); an int is the count
        # of member cards matching the current query, however many that
        # is (including 0 or all of them) — see set_search_match_count.
        self._search_match_count: int | None = None

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
        # Checked against the canvas background and every active theme
        # slot (not just black) so the selection outline stays visible on
        # a dark theme/background, where a fixed black would wash out --
        # same treatment as CardItem's own selection outline.
        pen_color = (
            QColor(selection_outline_color(self._document.theme))
            if self.isSelected()
            else Qt.GlobalColor.darkGray
        )
        outline = QPen(pen_color, pen_width)

        if stack.card_ids:
            # Bottom-of-pile first (card_ids' own order -- add_cards_to_stack
            # appends, so the last id is the most recently added/topmost
            # card), reversed to top-of-pile first for the band painters
            # below, which fill from the edge adjacent to the top face
            # (top of the pile) outward (bottom of the pile).
            colors_top_to_bottom = [
                QColor(self._document.get_slot(self._document.get_card(cid).color_slot).hex)
                for cid in reversed(stack.card_ids)
            ]
            self._paint_front_face_bands(painter, front, colors_top_to_bottom)
            self._paint_right_face_bands(painter, right, colors_top_to_bottom)
            top_slot = self._document.get_slot(
                self._document.get_card(stack.card_ids[-1]).color_slot
            )
            top_fill = QColor(top_slot.hex)
            top_text_hex = top_slot.text_color or auto_text_color(top_slot.hex)
        else:
            painter.setPen(outline)
            painter.setBrush(_RIGHT_FILL)
            painter.drawPolygon(right)
            painter.setBrush(_FRONT_FILL)
            painter.drawPolygon(front)
            self._paint_front_face_lines(painter, front)
            self._paint_right_face_lines(painter, right)
            top_fill = _TOP_FILL
            top_text_hex = "#000000"

        # Re-stroke both faces' outer silhouette on top of the bands (each
        # band paints its own thin border, which would otherwise leave the
        # face's outer edge at the wrong width/color once selected).
        painter.setPen(outline)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolygon(right)
        painter.drawPolygon(front)

        painter.setPen(outline)
        painter.setBrush(top_fill)
        painter.drawRect(top)
        painter.restore()

        self._paint_badge(painter, top, len(stack.card_ids))
        if stack.label:
            self._paint_label(painter, top, stack.label, top_text_hex)

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
        """Thin vertical lines across the right face, matching that
        face's own vertical orientation. Its left edge (at(0)-at(3)) and
        right edge (at(1)-at(2)) are both perfectly vertical (offset from
        each other only by the box's oblique depth), so — mirroring the
        front face's approach — lerping between the top edge
        (at(0)-at(1)) and bottom edge (at(3)-at(2)) at the same fraction
        produces lines parallel to those vertical edges, i.e. vertical
        lines themselves."""
        top_left, top_right = right.at(0), right.at(1)
        bottom_left, bottom_right = right.at(3), right.at(2)
        painter.save()
        painter.setPen(QPen(_EDGE_LINE_COLOR, 1))
        for i in range(1, _LINE_COUNT):
            t = i / _LINE_COUNT
            start = top_left + (top_right - top_left) * t
            end = bottom_left + (bottom_right - bottom_left) * t
            painter.drawLine(start, end)
        painter.restore()

    def _paint_bands(
        self,
        painter: QPainter,
        edge_a: tuple[QPointF, QPointF],
        edge_b: tuple[QPointF, QPointF],
        colors: list[QColor],
    ) -> None:
        """Fills the quadrilateral bounded by edge_a and edge_b -- each
        face's own pair of depth-direction edges, the same edges
        _paint_front_face_lines/_paint_right_face_lines already lerp
        along -- with one band per color, from edge_a[0]/edge_b[0] (t=0,
        adjacent to the top face: the top of the pile) to edge_a[1]/
        edge_b[1] (t=1, the fully-extruded outer corner: the bottom of
        the pile). One band per member card, in stack order, is what
        makes the stack's edge read the way a real stack of colored
        paper's edge would."""
        edge_a_start, edge_a_end = edge_a
        edge_b_start, edge_b_end = edge_b
        count = len(colors)
        painter.save()
        # NoPen, not a thin separator stroke: once a stack has enough
        # members that a band is only a pixel or two wide, a 1px border
        # drawn on every single band would dominate the whole face and
        # wash the colors out to solid gray -- adjacent fills abutting
        # directly still reads as banding via the color changes alone.
        painter.setPen(Qt.PenStyle.NoPen)
        for i, color in enumerate(colors):
            t0, t1 = i / count, (i + 1) / count
            a0 = edge_a_start + (edge_a_end - edge_a_start) * t0
            a1 = edge_a_start + (edge_a_end - edge_a_start) * t1
            b0 = edge_b_start + (edge_b_end - edge_b_start) * t0
            b1 = edge_b_start + (edge_b_end - edge_b_start) * t1
            painter.setBrush(color)
            painter.drawPolygon(QPolygonF([a0, a1, b1, b0]))
        painter.restore()

    def _paint_front_face_bands(
        self, painter: QPainter, front: QPolygonF, colors: list[QColor]
    ) -> None:
        top_left, bottom_left, bottom_right, top_right = (
            front.at(0),
            front.at(1),
            front.at(2),
            front.at(3),
        )
        self._paint_bands(painter, (top_left, bottom_left), (top_right, bottom_right), colors)

    def _paint_right_face_bands(
        self, painter: QPainter, right: QPolygonF, colors: list[QColor]
    ) -> None:
        top_left, top_right = right.at(0), right.at(1)
        bottom_left, bottom_right = right.at(3), right.at(2)
        self._paint_bands(painter, (top_left, top_right), (bottom_left, bottom_right), colors)

    def _paint_badge(self, painter: QPainter, top: QRectF, total_count: int) -> None:
        matching = self._search_match_count
        if matching is not None and matching > 0:
            text = f"{matching}/{total_count}"
            badge_color = _BADGE_MATCH_COLOR
        else:
            text = str(total_count)
            badge_color = _BADGE_COLOR
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
        painter.setBrush(badge_color)
        painter.setPen(Qt.PenStyle.NoPen)
        radius = badge_rect.height() / 2
        painter.drawRoundedRect(badge_rect, radius, radius)
        painter.setPen(QColor(Qt.GlobalColor.white))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()

    def _paint_label(self, painter: QPainter, top: QRectF, label: str, text_hex: str) -> None:
        metrics = QFontMetrics(painter.font())
        available_width = top.width() - 2 * _LABEL_MARGIN
        elided = metrics.elidedText(label, Qt.TextElideMode.ElideRight, int(available_width))

        painter.save()
        painter.setPen(QColor(text_hex))
        text_rect = top.adjusted(_LABEL_MARGIN, 0, -_LABEL_MARGIN, 0)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, elided)
        painter.restore()

    def refresh(self) -> None:
        self.update()

    def set_search_match_count(self, count: int | None) -> None:
        """count is None when there's no active search (default
        rendering); otherwise the number of member cards matching the
        current query (0 through every member). Zero de-emphasizes the
        whole item via reduced opacity, same idea as CardItem's dimming
        for a non-matching loose card; a positive count instead turns the
        count badge red and switches its text to "matching/total"."""
        if count == self._search_match_count:
            return
        self._search_match_count = count
        self.setOpacity(_DIMMED_OPACITY if count == 0 else 1.0)
        self.update()

    # -- drag ---------------------------------------------------------------

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        scene = self.scene()
        if scene is not None and hasattr(scene, "bring_item_to_front"):
            # Before super() changes selection as a side effect of this
            # press — bring_item_to_front reads current selection to decide
            # whether to raise just this stack or the whole group. Some
            # tests add a StackItem to a bare QGraphicsScene rather than a
            # real CanvasScene, hence the hasattr guard.
            scene.bring_item_to_front(self)
        if self._undo_stack is not None:
            self._press_pos = (self.pos().x(), self.pos().y())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        super().mouseMoveEvent(event)
        if self._undo_stack is not None and self._press_pos is not None:
            self._update_drop_highlight(event.scenePos())

    def _update_drop_highlight(self, scene_pos: QPointF) -> None:
        """Live preview of mouseReleaseEvent's own merge-target
        resolution, recomputed on every drag move via the same
        _resolve_merge_target() the release handler uses — so the glow
        can never promise a merge the drop wouldn't actually offer."""
        target = self._resolve_merge_target(scene_pos)
        if target is not self._drop_highlight_target:
            self._clear_drop_highlight()
            if target is not None:
                apply_drop_highlight(
                    target, True, self._document.canvas_background_color, dragged_item=self
                )
                self._drop_highlight_target = target

    def _clear_drop_highlight(self) -> None:
        if self._drop_highlight_target is not None:
            apply_drop_highlight(self._drop_highlight_target, False)
            self._drop_highlight_target = None

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        self._clear_drop_highlight()
        if self._undo_stack is None or self._press_pos is None:
            return
        old_pos = self._press_pos
        self._press_pos = None
        new_pos = (self.pos().x(), self.pos().y())
        if new_pos == old_pos:
            return

        target = self._resolve_merge_target(event.scenePos())
        if target is not None:
            parent_widget = (
                self.scene().views()[0] if self.scene() and self.scene().views() else None
            )
            dialog = CreateStackPromptDialog(
                "Merge these two stacks?", parent_widget, title="Merge Stacks"
            )
            if dialog.exec() == QDialog.DialogCode.Accepted:
                target_stack = self._document.get_stack(target.stack_id)
                new_stack = Stack(
                    id=new_stack_id(self._document.stacks.keys()),
                    x=target_stack.x,
                    y=target_stack.y,
                    label=dialog.label(),
                )
                self._undo_stack.push(
                    MergeStacksCommand(self._document, new_stack, self.stack_id, target.stack_id)
                )
                return

        self._undo_stack.push(MoveStackCommand(self._document, self.stack_id, old_pos, new_pos))

    def _resolve_merge_target(self, scene_pos: QPointF) -> StackItem | None:
        """Whatever other StackItem is under scene_pos, if any — same
        point-based hit-test convention as CardItem._resolve_drop_target,
        scoped to StackItem hits only (a stack dragged onto a loose card
        isn't a merge target) and excluding this item itself. Kept
        separate from CardItem's version rather than shared: the
        exclusion shape differs (a single self vs. a multi-card-drag
        exclude set) and this is only a handful of lines."""
        scene = self.scene()
        if scene is None:
            return None
        for item in scene.items(scene_pos):
            node = item
            while node is not None and not isinstance(node, StackItem):
                node = node.parentItem()
            if isinstance(node, StackItem) and node is not self:
                return node
        return None

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        scene = self.scene()
        if scene is None or not scene.views():
            event.ignore()
            return
        view = scene.views()[0]
        view.stack_overlay.open(self.stack_id, self._document, self._undo_stack)
        event.accept()

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
