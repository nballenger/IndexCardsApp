from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QColor,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsSceneContextMenuEvent,
    QGraphicsSceneHoverEvent,
    QGraphicsSceneMouseEvent,
    QMenu,
    QStyleOptionGraphicsItem,
    QWidget,
)

from indexcards.commands.region_commands import (
    ChangeRegionLabelCommand,
    MoveRegionCommand,
    RemoveRegionCommand,
    ResizeRegionCommand,
    push_region_growth_result,
)
from indexcards.models.document import Document
from indexcards.models.region import CORNER_RADIUS, LABEL_BAR_HEIGHT, MIN_REGION_SIZE, Region
from indexcards.regions.geometry import contained_card_ids, contained_stack_ids, to_rect
from indexcards.regions.growth import resolve_region_growth
from indexcards.utils.contrast import auto_text_color, relative_luminance
from indexcards.widgets.region_dialogs import prompt_region_label

_BORDER_BAND = 8.0
_LABEL_MARGIN = 8.0
_DARK_BACKGROUND_LUMINANCE = 0.5
_BASE_Z_VALUE = -1000.0


class RegionItem(QGraphicsObject):
    """A labeled, resizable round-rect zone drawn behind cards and stacks.

    Not ItemIsMovable -- unlike CardItem/StackItem, a drag is only
    initiated from the label bar and driven manually (see mousePressEvent),
    which also lets it carry whatever cards/stacks were inside it at press
    time as one undo step. shape() excludes the body (only the label bar
    and a thin border band respond to the mouse), so rubber-band selection
    and double-click-to-create still work for anything inside a region.
    """

    def __init__(
        self,
        region_id: str,
        document: Document,
        undo_stack: QUndoStack | None = None,
        parent: QGraphicsItem | None = None,
    ) -> None:
        super().__init__(parent)
        self.region_id = region_id
        self._document = document
        self._undo_stack = undo_stack
        region = document.get_region(region_id)
        self._width = region.width
        self._height = region.height

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setAcceptHoverEvents(True)
        self._apply_z_value()

        self._drag_mode: str | None = None  # "move" | "resize" | None
        self._press_scene_pos: QPointF | None = None
        self._press_geometry: tuple[float, float, float, float] | None = None
        self._resize_edges: tuple[bool, bool, bool] = (False, False, False)  # left, right, bottom
        self._drag_region_ids: list[str] = []
        self._drag_region_old_geometries: dict[str, tuple[float, float, float, float]] = {}
        self._drag_region_card_ids: dict[str, list[str]] = {}
        self._drag_region_stack_ids: dict[str, list[str]] = {}
        self._drag_old_card_positions: dict[str, tuple[float, float]] = {}
        self._drag_old_stack_positions: dict[str, tuple[float, float]] = {}

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._width, self._height)

    def shape(self) -> QPainterPath:
        outer = QPainterPath()
        outer.addRoundedRect(self.boundingRect(), CORNER_RADIUS, CORNER_RADIUS)
        hole_width = self._width - 2 * _BORDER_BAND
        hole_height = self._height - LABEL_BAR_HEIGHT - _BORDER_BAND
        if hole_width > 0 and hole_height > 0:
            hole = QPainterPath()
            hole.addRect(QRectF(_BORDER_BAND, LABEL_BAR_HEIGHT, hole_width, hole_height))
            outer = outer.subtracted(hole)
        return outer

    # -- paint ---------------------------------------------------------------

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        try:
            region = self._document.get_region(self.region_id)
        except KeyError:
            # Removed mid-dispatch (e.g. a deferred delete); an exception
            # raised inside paint() segfaults rather than raising normally.
            return

        background_hex = self._document.canvas_background_color
        ink_hex, alpha = self._tint_ink(background_hex)
        fill = QColor(ink_hex)
        fill.setAlpha(alpha)
        rect = self.boundingRect()
        outer_path = QPainterPath()
        outer_path.addRoundedRect(rect, CORNER_RADIUS, CORNER_RADIUS)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(fill)
        pen_width = 2 if self.isSelected() else 1.5
        painter.setPen(QPen(QColor(ink_hex), pen_width))
        painter.drawPath(outer_path)

        # A solid title bar -- same color as the border, opaque, clipped to
        # the region's own rounded outline so only its top two corners
        # round off -- drawn unconditionally (even with no label set),
        # since this whole strip is now excluded from card placement too
        # (see regions.geometry.interior_rect) and should always read as
        # visually distinct.
        painter.setClipPath(outer_path)
        painter.fillRect(QRectF(0, 0, rect.width(), LABEL_BAR_HEIGHT), QColor(ink_hex))
        painter.setClipping(False)

        if region.label:
            text_color = auto_text_color(ink_hex)
            metrics = QFontMetrics(painter.font())
            available_width = rect.width() - 2 * _LABEL_MARGIN
            elided = metrics.elidedText(
                region.label, Qt.TextElideMode.ElideRight, int(max(available_width, 0))
            )
            label_rect = QRectF(0, 0, rect.width(), LABEL_BAR_HEIGHT).adjusted(
                _LABEL_MARGIN, 0, -_LABEL_MARGIN, 0
            )
            painter.setPen(QColor(text_color))
            painter.drawText(
                label_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided
            )
        painter.restore()

    @staticmethod
    def _tint_ink(background_hex: str) -> tuple[str, int]:
        """White at ~10% alpha over a dark background, black at ~8% over a
        light one -- both read as a faint sheet of paper regardless of
        theme, without competing with card-color status coding."""
        if relative_luminance(background_hex) < _DARK_BACKGROUND_LUMINANCE:
            return "#ffffff", 26  # ~10% of 255
        return "#000000", 20  # ~8% of 255

    def refresh(self) -> None:
        region = self._document.get_region(self.region_id)
        if (region.width, region.height) != (self._width, self._height):
            self.prepareGeometryChange()
            self._width = region.width
            self._height = region.height
            self._apply_z_value()
        self.update()

    def _apply_z_value(self) -> None:
        """Every region sits below cards/stacks/links (which are z >= 1);
        among regions, a smaller (more likely nested) one sits above a
        larger one, so a region drawn inside another isn't hidden by it."""
        area = self._width * self._height
        self.setZValue(_BASE_Z_VALUE - area / 1_000_000)

    # -- drag: move (label bar) or resize (border band) ----------------------

    def _zone_at(self, local_pos: QPointF) -> str | None:
        x, y = local_pos.x(), local_pos.y()
        if 0 <= y <= LABEL_BAR_HEIGHT and 0 <= x <= self._width:
            return "move"
        left = x <= _BORDER_BAND
        right = x >= self._width - _BORDER_BAND
        bottom = y >= self._height - _BORDER_BAND
        if left or right or bottom:
            return "resize"
        return None

    def _resize_cursor(self, local_pos: QPointF) -> Qt.CursorShape:
        left, right, bottom = self._edges_at(local_pos)
        if left and bottom:
            return Qt.CursorShape.SizeBDiagCursor
        if right and bottom:
            return Qt.CursorShape.SizeFDiagCursor
        if left or right:
            return Qt.CursorShape.SizeHorCursor
        return Qt.CursorShape.SizeVerCursor

    def _edges_at(self, local_pos: QPointF) -> tuple[bool, bool, bool]:
        x, y = local_pos.x(), local_pos.y()
        left = x <= _BORDER_BAND
        right = x >= self._width - _BORDER_BAND
        bottom = y >= self._height - _BORDER_BAND
        return left, right, bottom

    def hoverMoveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        zone = self._zone_at(event.pos())
        if zone == "move":
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        elif zone == "resize":
            self.setCursor(self._resize_cursor(event.pos()))
        else:
            self.unsetCursor()
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        self.unsetCursor()
        super().hoverLeaveEvent(event)

    def _selection_scoped_region_ids(self) -> list[str]:
        """The regions a label-bar drag should move together: the whole
        current selection if this region is part of one, otherwise just
        this region -- matching CardItem's identical convention (see
        card_item.py's _selection_scoped_card_ids), so clicking an
        unselected region while others are selected replaces the
        selection and drags only that one."""
        scene = self.scene()
        if scene is not None and self.isSelected():
            selected_ids = scene.selected_region_ids()
            if self.region_id in selected_ids:
                return selected_ids
        return [self.region_id]

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        # Captured before super() (which may change selection as a side
        # effect of this press) so this reflects the selection as it stood
        # going into the drag -- see _selection_scoped_region_ids.
        drag_group_ids = self._selection_scoped_region_ids()
        super().mousePressEvent(event)
        if self._undo_stack is None:
            return
        zone = self._zone_at(event.pos())
        if zone is None:
            return
        region = self._document.get_region(self.region_id)
        self._press_scene_pos = event.scenePos()
        self._press_geometry = (region.x, region.y, region.width, region.height)
        if zone == "move":
            self._drag_mode = "move"
            self._resize_edges = (False, False, False)
            self._drag_region_ids = drag_group_ids
            claimed_card_ids: set[str] = set()
            claimed_stack_ids: set[str] = set()
            self._drag_region_card_ids = {}
            self._drag_region_stack_ids = {}
            self._drag_region_old_geometries = {}
            self._drag_old_card_positions = {}
            self._drag_old_stack_positions = {}
            for region_id in drag_group_ids:
                member = self._document.get_region(region_id)
                self._drag_region_old_geometries[region_id] = (
                    member.x, member.y, member.width, member.height,
                )
                card_ids = [
                    cid
                    for cid in contained_card_ids(member, self._document.iter_cards())
                    if cid not in claimed_card_ids
                ]
                stack_ids = [
                    sid
                    for sid in contained_stack_ids(member, self._document.iter_stacks())
                    if sid not in claimed_stack_ids
                ]
                claimed_card_ids.update(card_ids)
                claimed_stack_ids.update(stack_ids)
                self._drag_region_card_ids[region_id] = card_ids
                self._drag_region_stack_ids[region_id] = stack_ids
                for card_id in card_ids:
                    card = self._document.get_card(card_id)
                    self._drag_old_card_positions[card_id] = (card.x, card.y)
                for stack_id in stack_ids:
                    stack = self._document.get_stack(stack_id)
                    self._drag_old_stack_positions[stack_id] = (stack.x, stack.y)
        else:
            self._drag_mode = "resize"
            self._resize_edges = self._edges_at(event.pos())

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._drag_mode is None or self._press_scene_pos is None or self._press_geometry is None:
            super().mouseMoveEvent(event)
            return
        delta = event.scenePos() - self._press_scene_pos
        start_x, start_y, start_width, start_height = self._press_geometry

        scene = self.scene()
        if self._drag_mode == "move":
            self.setPos(start_x + delta.x(), start_y + delta.y())
            if scene is not None and hasattr(scene, "item_for_card"):
                for region_id in self._drag_region_ids:
                    if region_id == self.region_id:
                        continue
                    ox, oy = self._drag_region_old_geometries[region_id][:2]
                    other_item = scene.item_for_region(region_id)
                    if other_item is not None:
                        other_item.setPos(ox + delta.x(), oy + delta.y())
                for card_id, (ox, oy) in self._drag_old_card_positions.items():
                    item = scene.item_for_card(card_id)
                    if item is not None:
                        item.setPos(ox + delta.x(), oy + delta.y())
                for stack_id, (ox, oy) in self._drag_old_stack_positions.items():
                    item = scene.item_for_stack(stack_id)
                    if item is not None:
                        item.setPos(ox + delta.x(), oy + delta.y())
        else:
            left, right, bottom = self._resize_edges
            new_x, new_width = start_x, start_width
            if left:
                new_width = max(start_width - delta.x(), MIN_REGION_SIZE[0])
                new_x = start_x + (start_width - new_width)
            elif right:
                new_width = max(start_width + delta.x(), MIN_REGION_SIZE[0])
            new_height = start_height
            if bottom:
                new_height = max(start_height + delta.y(), MIN_REGION_SIZE[1])
            self.prepareGeometryChange()
            self._width = new_width
            self._height = new_height
            self.setPos(new_x, start_y)
            self.update()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        if self._drag_mode is None or self._press_geometry is None:
            self._reset_drag_state()
            return

        if self._drag_mode == "move":
            self._finish_move()
        else:
            self._finish_resize()
        self._reset_drag_state()

    def _finish_move(self) -> None:
        group = self._drag_region_ids
        old = self._drag_region_old_geometries
        drag_dx = self.pos().x() - old[self.region_id][0]
        drag_dy = self.pos().y() - old[self.region_id][1]
        if drag_dx == 0.0 and drag_dy == 0.0:
            return  # nothing moved -- live-dragged children never left their old positions

        # Every OTHER group member enters resolve_region_growth's region
        # list already at its post-drag (rigidly translated) geometry --
        # the function only special-cases ONE id via its own
        # changed_region_id/changed_geometry parameters; everything else
        # it reads comes as-is from `regions`.
        target = {
            region_id: (ox + drag_dx, oy + drag_dy, width, height)
            for region_id, (ox, oy, width, height) in old.items()
        }
        other_regions = [
            Region(
                id=region.id,
                x=target[region.id][0],
                y=target[region.id][1],
                width=target[region.id][2],
                height=target[region.id][3],
            )
            if region.id in target
            else region
            for region in self._document.iter_regions()
            if region.id != self.region_id
        ]
        diff = resolve_region_growth(
            self.region_id, target[self.region_id], other_regions, try_yield=len(group) == 1
        )
        if diff is None:
            self._revert_group_drag()
            return

        final = {region_id: diff.get(region_id, target[region_id]) for region_id in group}
        move_commands = []
        for region_id in group:
            region_dx = final[region_id][0] - old[region_id][0]
            region_dy = final[region_id][1] - old[region_id][1]
            card_ids = self._drag_region_card_ids.get(region_id, [])
            stack_ids = self._drag_region_stack_ids.get(region_id, [])
            move_commands.append(
                MoveRegionCommand(
                    self._document,
                    region_id,
                    old[region_id][:2],
                    final[region_id][:2],
                    {cid: self._drag_old_card_positions[cid] for cid in card_ids},
                    {
                        cid: (
                            self._drag_old_card_positions[cid][0] + region_dx,
                            self._drag_old_card_positions[cid][1] + region_dy,
                        )
                        for cid in card_ids
                    },
                    {sid: self._drag_old_stack_positions[sid] for sid in stack_ids},
                    {
                        sid: (
                            self._drag_old_stack_positions[sid][0] + region_dx,
                            self._drag_old_stack_positions[sid][1] + region_dy,
                        )
                        for sid in stack_ids
                    },
                )
            )

        resize_commands = []
        for region_id in group:
            if final[region_id][2:] != old[region_id][2:]:
                resize_commands.append(
                    ResizeRegionCommand(self._document, region_id, old[region_id], final[region_id])
                )
        for region_id, geometry in diff.items():
            if region_id not in group:  # an outside region forced to grow, never repositioned
                old_geometry = to_rect(self._document.get_region(region_id))
                resize_commands.append(
                    ResizeRegionCommand(self._document, region_id, old_geometry, geometry)
                )

        commands = move_commands + resize_commands
        if len(commands) == 1:
            self._undo_stack.push(commands[0])
        else:
            self._undo_stack.beginMacro("Move Regions" if len(group) > 1 else "Move Region")
            for command in commands:
                self._undo_stack.push(command)
            self._undo_stack.endMacro()

    def _revert_group_drag(self) -> None:
        scene = self.scene()
        for region_id in self._drag_region_ids:
            item = self if region_id == self.region_id else (
                scene.item_for_region(region_id) if scene is not None else None
            )
            if item is not None:
                item.setPos(*self._drag_region_old_geometries[region_id][:2])
        if scene is not None:
            for card_id, position in self._drag_old_card_positions.items():
                item = scene.item_for_card(card_id)
                if item is not None:
                    item.setPos(*position)
            for stack_id, position in self._drag_old_stack_positions.items():
                item = scene.item_for_stack(stack_id)
                if item is not None:
                    item.setPos(*position)

    def _finish_resize(self) -> None:
        new_geometry = (self.pos().x(), self.pos().y(), self._width, self._height)
        if new_geometry == self._press_geometry:
            return

        other_regions = [
            region for region in self._document.iter_regions() if region.id != self.region_id
        ]
        diff = resolve_region_growth(
            self.region_id, new_geometry, other_regions, try_yield=False
        )
        if diff is None:
            old_x, old_y, old_width, old_height = self._press_geometry
            self.prepareGeometryChange()
            self._width, self._height = old_width, old_height
            self.setPos(old_x, old_y)
            self.update()
            return

        # If resizing this region also left ITS OWN moat over some other
        # region too tight, diff includes a further-grown geometry for it
        # (an own-face violation is always fixed by growing that region,
        # regardless of gesture) -- use that as the final geometry rather
        # than the raw, un-grown drag target, or that extra growth would
        # be silently computed and then discarded.
        final_geometry = diff.get(self.region_id, new_geometry)
        resize_command = ResizeRegionCommand(
            self._document, self.region_id, self._press_geometry, final_geometry
        )
        other_diffs = {rid: geometry for rid, geometry in diff.items() if rid != self.region_id}
        push_region_growth_result(self._undo_stack, self._document, resize_command, other_diffs)

    def _reset_drag_state(self) -> None:
        self._drag_mode = None
        self._press_scene_pos = None
        self._press_geometry = None
        self._drag_region_ids = []
        self._drag_region_old_geometries = {}
        self._drag_region_card_ids = {}
        self._drag_region_stack_ids = {}
        self._drag_old_card_positions = {}
        self._drag_old_stack_positions = {}

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._zone_at(event.pos()) == "move":
            self._edit_label_via_dialog()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    # -- context menu ---------------------------------------------------------

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:
        if self._undo_stack is None:
            event.ignore()
            return
        menu, label_action, delete_action = self._build_context_menu()
        chosen = menu.exec(event.screenPos())
        if chosen is label_action:
            self._edit_label_via_dialog()
        elif chosen is delete_action:
            self._delete_via_menu()

    def _build_context_menu(self) -> tuple[QMenu, QAction, QAction]:
        """Builds the menu without exec()'ing it, so tests can inspect its
        contents without triggering a real, blocking modal popup."""
        region = self._document.get_region(self.region_id)
        menu = QMenu()
        label_action = menu.addAction("Change Label..." if region.label else "Label...")
        menu.addSeparator()
        delete_action = menu.addAction("Delete Region")
        return menu, label_action, delete_action

    def _edit_label_via_dialog(self) -> None:
        region = self._document.get_region(self.region_id)
        parent_widget = self.scene().views()[0] if self.scene() and self.scene().views() else None
        new_label = prompt_region_label(parent_widget, "Label Region", region.label)
        if new_label is None or new_label == region.label:
            return
        self._undo_stack.push(
            ChangeRegionLabelCommand(self._document, self.region_id, region.label, new_label)
        )

    def _delete_via_menu(self) -> None:
        # Deferred: this handler is on the item's own event-dispatch call
        # stack, and Qt doesn't tolerate an item being torn down while
        # still on it. Locals are captured now, not looked up via self.
        # later, since self may be gone by the time the timer fires.
        document = self._document
        undo_stack = self._undo_stack
        region_id = self.region_id
        QTimer.singleShot(0, lambda: undo_stack.push(RemoveRegionCommand(document, region_id)))
