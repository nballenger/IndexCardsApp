from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import (
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter, QPen, QUndoStack, QWheelEvent
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsObject,
    QGraphicsScene,
    QGraphicsView,
    QWidget,
)

from indexcards.canvas.card_item import CardItem
from indexcards.canvas.stack_item import _STACK_DEPTH
from indexcards.commands.stack_commands import (
    ReorderStackCommand,
    push_create_card_in_stack,
    push_eject_card_from_stack,
)
from indexcards.models.card import DEFAULT_CARD_SIZE, Card
from indexcards.models.document import Document
from indexcards.models.stack import Stack
from indexcards.utils.ids import new_card_id

_CELL_SPACING = 24.0  # gap between tiles, and from the grid's own edge to its view's edge
_VIEWPORT_MARGIN_FRACTION = 0.1  # at least this much of the viewport stays bare scrim per side
_SCRIM_COLOR = QColor(20, 20, 20, 140)
_VIEW_FRAME_PADDING = 2  # room for the inner QGraphicsView's own frame
_SLIDE_DURATION_MS = 150  # sibling-reflow and snap-back animation length
_ARROW_KEY_DELTAS = {
    Qt.Key.Key_Left: (-1, 0),
    Qt.Key.Key_Right: (1, 0),
    Qt.Key.Key_Up: (0, -1),
    Qt.Key.Key_Down: (0, 1),
}  # (dcol, drow)
# The first ejected card clears the StackItem's own rendered footprint
# (a card's width plus its isometric "depth") entirely, landing a gutter
# to its right rather than mostly overlapping it.
_EJECT_GUTTER = 24.0
# Each subsequent eject in the same overlay session cascades diagonally
# from where the previous one landed, matching the step used when
# creating several new cards in a row (see card_table_model.py's
# _NEW_CARD_POSITION_STEP) — not the same constant (a different
# subsystem), but the same diagonal-cascade idea.
_EJECT_CASCADE_STEP = 20.0


class _StackGridView(QGraphicsView):
    """The overlay's inner grid view — hosts the tile CardItems and exists
    mainly to route keyboard input correctly: a tile mid-edit gets first
    refusal on Escape/arrows/Enter alike (forwarded to Qt's normal
    focus-item delivery, so its own _CardTextItem handles them as ordinary
    text editing — commit-and-exit for Escape, cursor movement for arrows,
    a newline for Enter), and only when no tile is currently editing are
    they treated as overlay-level navigation: Escape closes the overlay,
    arrow keys move the focused tile, Enter/Space opens the focused tile
    for editing.

    Deliberately checks each CardItem's own is_editing flag rather than
    scene().focusItem() to decide *whether* a tile is editing — real Qt
    widget focus can lag or fail to clear promptly when the containing
    window isn't genuinely OS-active (the same class of issue
    _CardTextItem.focusOutEvent already works around for
    ActiveWindowFocusReason), so is_editing is the more reliable signal.
    Actual delivery of the key event to commit/exit an active edit still
    goes through Qt's normal focus-item routing via super().keyPressEvent."""

    escapePressed = Signal()

    def __init__(
        self, scene: QGraphicsScene, overlay: StackOverlay, parent: QWidget | None = None
    ) -> None:
        super().__init__(scene, parent)
        self._overlay = overlay
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # Only vertical scrolling is wanted here (per design) — cols are
        # already capped to fit available width in _grid_metrics, so a
        # horizontal bar would only ever appear from Qt's own default
        # "as needed on both axes" policy, never from genuine overflow.
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        scene = self.scene()
        editing = scene is not None and any(
            isinstance(item, CardItem) and item.is_editing for item in scene.items()
        )
        if not editing:
            if event.key() == Qt.Key.Key_Escape:
                self.escapePressed.emit()
                event.accept()
                return
            if event.key() in _ARROW_KEY_DELTAS:
                dcol, drow = _ARROW_KEY_DELTAS[event.key()]
                if self._overlay._move_focus(dcol, drow):
                    event.accept()
                    return
            elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
                if self._overlay._activate_focused_tile():
                    event.accept()
                    return
        super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        # Mirrors CanvasView.mouseDoubleClickEvent's empty-space check
        # exactly: double-clicking a tile still falls through to
        # super().mouseDoubleClickEvent, which Qt forwards to the item
        # (CardItem.mouseDoubleClickEvent -> enter_edit_mode()) unchanged.
        # Only empty grid space -- no item under the cursor -- creates a
        # new card, so this stays inside the overlay instead of leaving
        # the double-click to bubble up and hit the scrim's dismiss-on-
        # press handling (StackOverlay.mousePressEvent).
        scene = self.scene()
        if scene is not None:
            scene_pos = self.mapToScene(event.position().toPoint())
            if scene.itemAt(scene_pos, self.transform()) is None:
                # Deferred, not called synchronously: create_card() pushes
                # a command that rebuilds this very scene (clearing and
                # recreating every tile) -- doing that while still inside
                # this view's own dispatch of the double-click that
                # triggered it is the same "don't delete/rebuild
                # mid-dispatch" hazard eject_card/the reorder-commit path
                # already guard against elsewhere in this file (see their
                # own docstrings), just reached via the view's widget-
                # level handler instead of an item's. Canceling the
                # scrim's own pending dismiss here too, defensively --
                # belt-and-suspenders alongside StackOverlay's own
                # mouseDoubleClickEvent, in case this press's own first
                # half ever reaches the scrim (e.g. an ignored, bubbled-up
                # QGraphicsView default press on empty space).
                self._overlay._dismiss_pending = False
                QTimer.singleShot(0, self._overlay.create_card)
                event.accept()
                return
        super().mouseDoubleClickEvent(event)


class OverlayCardItem(CardItem):
    """A StackOverlay tile used whenever the overlay has a real undo_stack
    (interactive stacks only — see StackOverlay._rebuild_tiles). Instead of
    CardItem's own drag-to-move-on-the-canvas behavior (which would push a
    MoveCardCommand using this item's pos() — grid-local here, never
    canvas coordinates), a drag reorders this card within the overlay's
    grid: siblings snap instantly to make room as the dragged tile crosses
    into their slot, and releasing either commits the new order (via the
    owning StackOverlay) or, if the order ended up unchanged, just snaps
    this tile back to its own slot."""

    def __init__(
        self,
        card_id: str,
        document: Document,
        undo_stack: QUndoStack,
        overlay: StackOverlay,
        get_minimum_font_size: Callable[[], int] | None = None,
    ) -> None:
        super().__init__(
            card_id,
            document,
            undo_stack=undo_stack,
            movable=True,
            get_minimum_font_size=get_minimum_font_size,
        )
        self._overlay = overlay
        self.add_position_listener(self._on_position_changed)

    def mousePressEvent(self, event) -> None:
        if self._editing:
            # A press elsewhere on the tile (outside the text item's own
            # rect) doesn't otherwise steal focus from it — commit and
            # drop out of edit mode before falling through to drag/select
            # handling, mirroring CardItem.mousePressEvent's own reasoning.
            self._text_item.clearFocus()
        scene = self.scene()
        modifiers = event.modifiers()
        extending_selection = bool(
            modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
        )
        if (
            scene is not None
            and not extending_selection
            and self.isSelected()
            and len(scene.selectedItems()) > 1
        ):
            # A plain press on a tile that's already part of a multi-
            # selection would otherwise drag every selected tile together
            # (Qt's own default behavior for ItemIsSelectable +
            # ItemIsMovable items, independent of anything in this file) —
            # not a fit for reordering, which only ever tracks one dragged
            # card. Collapsing to just this tile first means a plain drag
            # always moves one card; Ctrl/Shift-click still builds a
            # multi-selection normally (e.g. for a bulk color/pin change
            # via the context menu).
            scene.clearSelection()
            self.setSelected(True)
        # QGraphicsObject, not CardItem — deliberately skips
        # CardItem.mousePressEvent's _press_pos/_drag_group_ids bookkeeping,
        # which exists only to support MoveCardCommand and would be
        # meaningless (and wrong, if ever acted on) here.
        QGraphicsObject.mousePressEvent(self, event)
        self._overlay._on_tile_drag_started(self.card_id)

    def mouseReleaseEvent(self, event) -> None:
        # QGraphicsObject, not CardItem — skips CardItem.mouseReleaseEvent
        # entirely, so no MoveCardCommand/MoveCardsCommand path can ever
        # run for a grid-local position.
        QGraphicsObject.mouseReleaseEvent(self, event)
        if event.button() == Qt.MouseButton.LeftButton:
            self._refresh_cursor()
        self._overlay._on_tile_drag_finished(self.card_id)

    def _on_position_changed(self) -> None:
        self._overlay._on_tile_position_changed(self.card_id)


class StackOverlay(QWidget):
    """A floating, interactive overlay covering the full canvas viewport:
    double-clicking a Stack (see StackItem.mouseDoubleClickEvent) opens it
    here as a grid of its member cards, tiled using real CardItem
    instances — so inline text editing and the color/tag/pin context menu
    keep working exactly as they do on the main canvas — hosted in a
    dedicated QGraphicsScene that CanvasScene never sees and never
    coordinates with. Dismissed by Escape or a click outside the grid.

    Nothing about opening/closing is itself undoable or persisted; only
    edits made via a tile's own normal command paths are (same as any
    other CardItem)."""

    openedChanged = Signal(bool)

    def __init__(
        self, parent: QWidget, get_minimum_font_size: Callable[[], int] | None = None
    ) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._get_minimum_font_size = get_minimum_font_size
        self._document: Document | None = None
        self._stack_id: str | None = None
        self._undo_stack: QUndoStack | None = None
        self._tile_order: list[str] = []
        self._tiles: dict[str, CardItem] = {}
        self._dragging_card_id: str | None = None
        self._drag_start_order: list[str] | None = None
        self._eject_preview_pos: QPointF | None = None
        self._eject_cascade_count = 0
        self._animations: dict[str, QPropertyAnimation] = {}
        self._rebuild_pending = False
        self._dismiss_pending = False

        self._grid_scene = QGraphicsScene(self)
        self._grid_view = _StackGridView(self._grid_scene, self, self)
        self._grid_view.escapePressed.connect(self.dismiss)

        self.hide()

    @property
    def is_open(self) -> bool:
        return self._stack_id is not None

    def set_document(self, document: Document | None) -> None:
        """Called by CanvasView.setScene whenever the attached Document
        changes. Whatever stack_id is currently open almost certainly
        doesn't exist in the new document, so close defensively first."""
        if self.is_open:
            self.dismiss()
        self._document = document

    def open(self, stack_id: str, document: Document, undo_stack: QUndoStack | None) -> None:
        if self.is_open:
            self.dismiss()
        self._document = document
        self._stack_id = stack_id
        self._undo_stack = undo_stack
        self._eject_cascade_count = 0
        # A deferred dismiss scheduled by a still-in-flight click on a
        # previous session must never fire against this new one once its
        # timer eventually elapses.
        self._dismiss_pending = False
        self._connect_document()

        viewport_size = self.parentWidget().size()
        # The overlay's own position is otherwise never set anywhere, so it
        # can be left at whatever stale/uninitialized geometry Qt happened
        # to give this widget — pin it to the viewport's own origin
        # explicitly, every time, rather than relying on it having already
        # been correct.
        self.move(0, 0)
        self.resize(viewport_size)

        self._rebuild_tiles()
        self.raise_()
        self.show()
        self._grid_view.setFocus()
        self.openedChanged.emit(True)

    def dismiss(self) -> None:
        # Also refuses while a drag is active: a hidden/deleted item that
        # still believes it holds Qt's mouse grab would mean a later
        # mouseReleaseEvent gets delivered to a deleted object.
        if not self.is_open or self._dragging_card_id is not None:
            return
        self._disconnect_document()
        self._stop_all_animations()
        self._grid_scene.clear()
        self._tiles = {}
        self._tile_order = []
        self._stack_id = None
        self._undo_stack = None
        self.hide()
        parent = self.parentWidget()
        if parent is not None:
            parent.setFocus()
        self.openedChanged.emit(False)

    def reposition(self, viewport_size: QSize) -> None:
        """Called by CanvasView.resizeEvent, mirroring
        ColorKeyOverlay.reposition — a no-op while closed, since re-flowing
        a grid that has no tiles serves no purpose."""
        if not self.is_open:
            return
        self.move(0, 0)
        self.resize(viewport_size)
        self._layout_grid()

    # -- painting / input -------------------------------------------------------

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        try:
            painter.fillRect(self.rect(), _SCRIM_COLOR)
            if self._eject_preview_pos is not None:
                self._paint_eject_ghost(painter)
        finally:
            painter.end()

    def _paint_eject_ghost(self, painter: QPainter) -> None:
        """A simplified translucent color swatch standing in for the tile
        while it's dragged past the grid's edge — not a full re-render of
        CardItem's own paint() (text, tags, pin), which would need a
        manually transformed painter for comparatively little benefit
        here: this is a drag-continuity cue, not the genuine article."""
        width, height = DEFAULT_CARD_SIZE
        rect = QRectF(self._eject_preview_pos.x(), self._eject_preview_pos.y(), width, height)
        card = self._document.get_card(self._dragging_card_id)
        slot = self._document.get_slot(card.color_slot)
        color = QColor(slot.hex)
        color.setAlpha(180)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(color)
        painter.setPen(QPen(Qt.GlobalColor.white, 2))
        painter.drawRoundedRect(rect, 4, 4)
        painter.restore()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        # Only reached for presses landing on the overlay's own surface —
        # the scrim. A press over _grid_view is delivered straight to that
        # child widget instead (Qt routes to the topmost widget under the
        # cursor), so anything reaching this handler is, by construction,
        # outside the grid: no geometry check needed.
        #
        # Deferred rather than dismissing immediately: Qt delivers the
        # first press of what's about to become a double-click exactly
        # like an ordinary single press — it has no way to know a second
        # one is coming — so dismissing synchronously here would hide
        # this widget (and stop it receiving any further input) before
        # that second click could ever arrive, permanently precluding
        # mouseDoubleClickEvent below from firing for anything outside
        # _grid_view's own tight bounds around the tiles. Waiting one
        # double-click interval lets a following double-click cancel this
        # and create a card instead.
        event.accept()
        self._dismiss_pending = True
        QTimer.singleShot(QApplication.doubleClickInterval(), self._commit_deferred_dismiss)

    def _commit_deferred_dismiss(self) -> None:
        if not self._dismiss_pending:
            return  # canceled by a double-click that arrived in time
        self._dismiss_pending = False
        self.dismiss()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        # Only reached for a double-click landing on the scrim, same
        # construction as mousePressEvent above — a double-click over
        # _grid_view is handled by _StackGridView's own override instead,
        # which also distinguishes an empty grid cell from an existing
        # tile (not meaningful here, since nothing but the scrim itself
        # exists at this widget's level). Deferred for the same
        # mid-dispatch-scene-rebuild reason as _StackGridView's own
        # override.
        self._dismiss_pending = False
        QTimer.singleShot(0, self.create_card)
        event.accept()

    def wheelEvent(self, event: QWheelEvent) -> None:
        # Only reached for wheel/trackpad-scroll events landing on the
        # scrim, same reasoning as mousePressEvent above (_grid_view
        # handles its own wheel-scrolling directly for anything over the
        # grid). Unlike a press, an *unhandled* wheel event's default
        # QWidget behavior is to ignore() it, which Qt then redelivers to
        # the parent viewport — letting CanvasView's own wheelEvent
        # (pan, and Cmd+scroll zoom) fire right through what's supposed to
        # be a fully blocking overlay. Accepting it here without acting on
        # it stops that bubble-up cold.
        event.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        # Belt-and-suspenders: _grid_view normally holds focus and handles
        # Escape itself (see _StackGridView.keyPressEvent above); this only
        # matters if focus ever lands on the overlay widget directly.
        if event.key() == Qt.Key.Key_Escape:
            self.dismiss()
            event.accept()
            return
        super().keyPressEvent(event)

    # -- tiles / layout -----------------------------------------------------------

    def _rebuild_tiles(self) -> None:
        if self._dragging_card_id is not None:
            # A rebuild right now would tear down the very tile whose
            # mouse grab this drag still holds (e.g. the deferred command
            # from an earlier drag landing just as a new one starts) —
            # same hazard dismiss() already guards against mid-drag.
            # Defer it: _on_tile_drag_finished checks this flag once the
            # drag concludes, and skips its own (by-then-stale) outcome in
            # favor of just running the rebuild.
            self._rebuild_pending = True
            return
        previously_focused = self._focused_card_id()
        self._stop_all_animations()
        self._grid_scene.clear()
        self._tiles = {}
        stack = self._document.get_stack(self._stack_id)
        self._tile_order = list(stack.card_ids)
        for card_id in self._tile_order:
            if self._undo_stack is not None:
                tile = OverlayCardItem(
                    card_id,
                    self._document,
                    self._undo_stack,
                    self,
                    get_minimum_font_size=self._get_minimum_font_size,
                )
            else:
                # No undo_stack: a non-interactive stack — tiles stay
                # read-only and non-reorderable, same as M1.
                tile = CardItem(
                    card_id,
                    self._document,
                    undo_stack=None,
                    movable=False,
                    get_minimum_font_size=self._get_minimum_font_size,
                )
            self._grid_scene.addItem(tile)
            self._tiles[card_id] = tile
        self._layout_grid()
        if self._tile_order:
            # Keep keyboard focus on the same card across a live rebuild
            # (e.g. a reorder commit, or an edit made elsewhere) when it's
            # still present; otherwise fall back to the first tile so arrow
            # navigation always has somewhere to start from.
            still_present = previously_focused in self._tile_order
            focus_id = previously_focused if still_present else self._tile_order[0]
            self._focus_tile(focus_id)

    def refresh_tiles(self) -> None:
        """Called after AppSettings.minimum_font_size changes, so a
        currently-open overlay's tiles pick up the new floor immediately
        rather than waiting for their next unrelated refresh — mirrors
        CanvasScene.refresh_text_fit()."""
        for tile in self._tiles.values():
            tile.refresh()

    def _grid_metrics(self) -> tuple[int, int, float, float]:
        """Returns (cols, rows, cell_w, cell_h) for the current tile count
        and viewport size — shared by the full layout pass, the drag-time
        nearest-slot lookup, and single-tile reflow, which must all agree
        on the same geometry."""
        width, height = DEFAULT_CARD_SIZE
        cell_w, cell_h = width + _CELL_SPACING, height + _CELL_SPACING

        parent = self.parentWidget()
        viewport_size = parent.size() if parent is not None else self.size()
        available_w = max(cell_w, viewport_size.width() * (1 - 2 * _VIEWPORT_MARGIN_FRACTION))

        count = len(self._tile_order)
        cols = max(1, min(count, int(available_w // cell_w))) if count else 1
        rows = -(-count // cols) if cols else 0
        return cols, rows, cell_w, cell_h

    def _slot_pos(self, index: int, cols: int, cell_w: float, cell_h: float) -> QPointF:
        row, col = divmod(index, cols)
        return QPointF(_CELL_SPACING / 2 + col * cell_w, _CELL_SPACING / 2 + row * cell_h)

    def _reflow(self, skip_card_id: str | None = None, animate: bool = False) -> None:
        """Repositions every tile per the current self._tile_order, without
        touching _grid_view's own size/position — used both for a full,
        instant layout pass (see _layout_grid) and, mid-drag, to slide
        sibling tiles into their new slots while skipping the
        actively-dragged one (which keeps following the mouse freely until
        release). animate=True is only ever appropriate for the latter —
        an initial layout or a resize should snap into place immediately,
        not visibly slide every tile on open/resize."""
        cols, _rows, cell_w, cell_h = self._grid_metrics()
        for index, card_id in enumerate(self._tile_order):
            if card_id == skip_card_id:
                continue
            target = self._slot_pos(index, cols, cell_w, cell_h)
            tile = self._tiles[card_id]
            if animate:
                self._animate_to(tile, target)
            else:
                tile.setPos(target)

    def _animate_to(self, tile: CardItem, target: QPointF) -> None:
        """Slides tile to target over _SLIDE_DURATION_MS rather than
        jumping instantly. Replaces (rather than stacks on top of) any
        animation already in flight for this same tile — e.g. a rapid
        back-and-forth drag that sends a sibling through several slots in
        quick succession — so the new animation continues smoothly from
        wherever the interrupted one had actually reached, not from its
        original starting point."""
        existing = self._animations.pop(tile.card_id, None)
        if existing is not None:
            existing.stop()
        if tile.pos() == target:
            return
        animation = QPropertyAnimation(tile, b"pos", self)
        animation.setDuration(_SLIDE_DURATION_MS)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.setStartValue(tile.pos())
        animation.setEndValue(target)
        card_id = tile.card_id
        animation.finished.connect(lambda: self._animations.pop(card_id, None))
        self._animations[card_id] = animation
        animation.start()

    def _stop_all_animations(self) -> None:
        """Halts every in-flight slide immediately (leaving each tile at
        whatever position it had reached) — must run before
        _grid_scene.clear() deletes the tiles those animations target, or
        a still-running QPropertyAnimation's next tick would try to set a
        property on an already-deleted QGraphicsItem."""
        for animation in list(self._animations.values()):
            animation.stop()
        self._animations.clear()

    def _nearest_slot_index(self, point: QPointF) -> int:
        cols, _rows, cell_w, cell_h = self._grid_metrics()
        half = QPointF(cell_w, cell_h) / 2
        best_index, best_dist = 0, None
        for index in range(len(self._tile_order)):
            center = self._slot_pos(index, cols, cell_w, cell_h) + half
            delta = point - center
            dist = delta.x() ** 2 + delta.y() ** 2
            if best_dist is None or dist < best_dist:
                best_index, best_dist = index, dist
        return best_index

    def _layout_grid(self) -> None:
        cols, rows, cell_w, cell_h = self._grid_metrics()
        self._reflow()

        grid_w = cols * cell_w + _CELL_SPACING / 2
        grid_h = rows * cell_h + _CELL_SPACING / 2
        self._grid_scene.setSceneRect(0, 0, grid_w, grid_h)

        parent = self.parentWidget()
        viewport_size = parent.size() if parent is not None else self.size()
        available_w = max(cell_w, viewport_size.width() * (1 - 2 * _VIEWPORT_MARGIN_FRACTION))
        available_h = max(cell_h, viewport_size.height() * (1 - 2 * _VIEWPORT_MARGIN_FRACTION))
        view_w = min(grid_w, available_w) + _VIEW_FRAME_PADDING
        view_h = min(grid_h, available_h) + _VIEW_FRAME_PADDING
        self._grid_view.resize(int(view_w), int(view_h))
        self._grid_view.move(
            int((viewport_size.width() - self._grid_view.width()) / 2),
            int((viewport_size.height() - self._grid_view.height()) / 2),
        )

    # -- drag-to-reorder / drag-out-to-eject -------------------------------------

    def _is_within_grid(self, point: QPointF) -> bool:
        cols, rows, cell_w, cell_h = self._grid_metrics()
        grid_w = cols * cell_w + _CELL_SPACING / 2
        grid_h = rows * cell_h + _CELL_SPACING / 2
        return 0 <= point.x() <= grid_w and 0 <= point.y() <= grid_h

    def _map_grid_point_to_overlay(self, scene_point: QPointF) -> QPointF:
        view_point = self._grid_view.mapFromScene(scene_point)
        return QPointF(self._grid_view.pos()) + QPointF(view_point)

    def _next_eject_position(self, stack: Stack) -> tuple[float, float]:
        """The first card ejected in this overlay session lands a clear
        gutter to the right of the Stack's own rendered footprint — not
        overlapping it. Each subsequent eject in the same session cascades
        diagonally from there (see _EJECT_CASCADE_STEP), so a run of
        ejects doesn't pile up on the exact same spot."""
        stack_width = DEFAULT_CARD_SIZE[0] + _STACK_DEPTH
        base_x = stack.x + stack_width + _EJECT_GUTTER
        base_y = stack.y
        step = _EJECT_CASCADE_STEP * self._eject_cascade_count
        self._eject_cascade_count += 1
        return (base_x + step, base_y + step)

    def _ghost_rect(self, top_left: QPointF) -> QRect:
        width, height = DEFAULT_CARD_SIZE
        margin = 4  # headroom for the ghost's own pen width
        return QRect(
            int(top_left.x()) - margin,
            int(top_left.y()) - margin,
            int(width) + 2 * margin,
            int(height) + 2 * margin,
        )

    def eject_card(self, card_id: str) -> None:
        """Removes card_id from the stack, landing it beside the Stack on
        the canvas — the same outcome dragging it past the grid's edge
        produces (see _on_tile_drag_finished above), triggered instead from
        a tile's "Remove from Stack" context-menu action or Edit > Remove
        from Stack."""
        if card_id not in self._tiles:
            return
        stack = self._document.get_stack(self._stack_id)
        new_position = self._next_eject_position(stack)
        document, stack_id, undo_stack = self._document, self._stack_id, self._undo_stack
        # Deferred for the same reason as the reorder push below: a
        # context-menu dispatch is still logically "inside" the tile's own
        # event handling when menu.exec() returns, so deleting the tile
        # synchronously here risks the same mid-event-dispatch hazard.
        QTimer.singleShot(
            0,
            lambda: push_eject_card_from_stack(
                undo_stack, document, stack_id, card_id, new_position
            ),
        )

    def create_card(self) -> str | None:
        """Creates a new card directly inside the open stack and enters
        edit mode on it, without leaving the overlay — the overlay's own
        analog of MainWindow._select_and_focus_new_card. No-op if closed
        or read-only (no undo_stack). _rebuild_tiles() (triggered
        synchronously by push_create_card_in_stack, via
        stackChanged -> _on_stack_changed) re-selects whichever tile was
        focused before this call, so focus/edit mode is set explicitly
        afterward to land on the new tile instead."""
        if not self.is_open or self._undo_stack is None:
            return None
        stack = self._document.get_stack(self._stack_id)
        card_id = new_card_id(self._document.cards.keys())
        card = Card(
            id=card_id,
            text=f"New Card {len(self._document.cards) + 1}",
            x=stack.x,
            y=stack.y,
            color_slot=self._document.theme.slots[0].id,
        )
        push_create_card_in_stack(self._undo_stack, self._document, self._stack_id, card)
        tile = self._tiles.get(card_id)
        if tile is not None:
            self._focus_tile(card_id)
            tile.enter_edit_mode()
        return card_id

    @property
    def selected_card_id(self) -> str | None:
        """Whichever tile currently holds keyboard focus (see
        _focused_card_id), for MainWindow's Edit > Remove from Stack to act
        on."""
        return self._focused_card_id()

    def _on_tile_drag_started(self, card_id: str) -> None:
        self._dragging_card_id = card_id
        self._drag_start_order = list(self._tile_order)

    def _on_tile_position_changed(self, card_id: str) -> None:
        # add_position_listener's callback fires for ANY position change,
        # including the ones _reflow() above performs on OTHER (sibling)
        # tiles — without this guard, repositioning a sibling would
        # trigger ITS OWN listener, recursively recomputing reorder logic
        # for a tile nobody is actually dragging.
        if card_id != self._dragging_card_id:
            return
        tile = self._tiles[card_id]
        width, height = DEFAULT_CARD_SIZE
        center = tile.pos() + QPointF(width / 2, height / 2)
        if self._is_within_grid(center):
            if self._eject_preview_pos is not None:
                # Came back inside the grid — clear the ghost, repainting
                # only the (small) region it occupied. The grid itself
                # repaints its own tiles automatically via the normal
                # QGraphicsScene item-position mechanism, so no self.update()
                # is needed for the reorder below — calling it on every
                # in-grid drag move would invalidate this whole
                # viewport-sized widget dozens of times a second for no
                # visible benefit, competing for paint time with unrelated,
                # rarer repaints elsewhere (e.g. the Stack's own card-count
                # badge on the canvas underneath, which only needs to
                # repaint once per eject and can otherwise end up queued
                # behind a steady stream of full-widget scrim repaints for
                # the entire span of a drag).
                self.update(self._ghost_rect(self._eject_preview_pos))
                self._eject_preview_pos = None
            target_index = self._nearest_slot_index(center)
            current_index = self._tile_order.index(card_id)
            if target_index != current_index:
                self._tile_order.pop(current_index)
                self._tile_order.insert(target_index, card_id)
                self._reflow(skip_card_id=card_id, animate=True)  # slide siblings into place
        else:
            # Past the grid's edge: no reorder bookkeeping (leave
            # _tile_order at its last valid in-grid state) — instead track
            # a ghost position so paintEvent can keep the drag visible over
            # the scrim. The real tile is left alone (no setPos/setVisible
            # games): QGraphicsView already clips anything outside its own
            # viewport for free, so it naturally stops rendering as it
            # crosses the boundary, and the ghost picks up from there.
            old_pos = self._eject_preview_pos
            new_pos = self._map_grid_point_to_overlay(tile.pos())
            self._eject_preview_pos = new_pos
            dirty = self._ghost_rect(new_pos)
            if old_pos is not None:
                dirty = dirty.united(self._ghost_rect(old_pos))
            self.update(dirty)

    def _on_tile_drag_finished(self, card_id: str) -> None:
        self._dragging_card_id = None
        if self._eject_preview_pos is not None:
            self.update(self._ghost_rect(self._eject_preview_pos))
            self._eject_preview_pos = None
        start_order = self._drag_start_order
        self._drag_start_order = None
        if self._rebuild_pending:
            # The stack's own data already changed while this drag was
            # still in progress — whatever this drag itself would have
            # produced is moot now, since the tiles it operated on are
            # about to be replaced wholesale by the rebuild that was
            # deferred until the drag (and its mouse grab) concluded.
            self._rebuild_pending = False
            self._rebuild_tiles()
            return
        tile = self._tiles[card_id]
        width, height = DEFAULT_CARD_SIZE
        center = tile.pos() + QPointF(width / 2, height / 2)

        if not self._is_within_grid(center):
            self.eject_card(card_id)
            return

        if self._tile_order == start_order:
            # No reorder happened — slide this one tile back to its own
            # slot. Safe to do directly (not deferred): no deletion/rebuild
            # involved, unlike the committed-reorder path below.
            cols, _rows, cell_w, cell_h = self._grid_metrics()
            target = self._slot_pos(self._tile_order.index(card_id), cols, cell_w, cell_h)
            self._animate_to(tile, target)
            return
        # Deferred: pushing now would run ReorderStackCommand.redo() ->
        # stackChanged -> _on_stack_changed -> _rebuild_tiles() ->
        # _grid_scene.clear(), deleting the very OverlayCardItem whose own
        # mouseReleaseEvent is still on the call stack right now — Qt does
        # not tolerate an item being deleted mid-event-dispatch (same
        # hazard family as an unhandled exception inside paint()). Capture
        # everything the callback needs as local values now, not via
        # self.<attr> lookups performed later — the overlay could in
        # principle be dismissed (clearing those attrs) in the brief
        # window before the timer fires, and the reorder should still
        # commit correctly even then.
        document, stack_id, undo_stack = self._document, self._stack_id, self._undo_stack
        new_order = list(self._tile_order)
        QTimer.singleShot(
            0,
            lambda: undo_stack.push(
                ReorderStackCommand(document, stack_id, start_order, new_order)
            ),
        )

    # -- keyboard navigation -----------------------------------------------------

    def _focused_card_id(self) -> str | None:
        """The keyboard-navigation "focus" is just whichever tile is
        currently selected — reusing CardItem's existing selection visual
        (a thicker border) rather than inventing a separate indicator, and
        automatically staying in sync with mouse-driven selection too."""
        for card_id, tile in self._tiles.items():
            if tile.isSelected():
                return card_id
        return None

    def _focus_tile(self, card_id: str) -> None:
        self._grid_scene.clearSelection()
        tile = self._tiles.get(card_id)
        if tile is not None:
            tile.setSelected(True)
            self._grid_view.ensureVisible(tile)

    def _move_focus(self, dcol: int, drow: int) -> bool:
        """Moves focus to the adjacent tile in the given direction, if one
        exists — returns False (leaving focus untouched) at the grid's
        edge rather than wrapping, and if nothing is focused yet, focuses
        the first tile regardless of which direction was pressed."""
        if not self._tile_order:
            return False
        current_id = self._focused_card_id()
        if current_id is None:
            self._focus_tile(self._tile_order[0])
            return True
        cols, rows, _cell_w, _cell_h = self._grid_metrics()
        current_index = self._tile_order.index(current_id)
        row, col = divmod(current_index, cols)
        new_row, new_col = row + drow, col + dcol
        if not (0 <= new_row < rows and 0 <= new_col < cols):
            return False
        target_index = new_row * cols + new_col
        if target_index >= len(self._tile_order):
            return False
        self._focus_tile(self._tile_order[target_index])
        return True

    def _activate_focused_tile(self) -> bool:
        card_id = self._focused_card_id()
        if card_id is None:
            return False
        # enter_edit_mode() is already a no-op on a read-only tile (no
        # undo_stack) — no need to special-case that here too.
        self._tiles[card_id].enter_edit_mode()
        return True

    # -- document reactivity ---------------------------------------------------

    def _connect_document(self) -> None:
        self._document.cardChanged.connect(self._on_card_changed)
        self._document.cardRemoved.connect(self._on_card_removed)
        self._document.stackChanged.connect(self._on_stack_changed)
        self._document.stackRemoved.connect(self._on_stack_removed)

    def _disconnect_document(self) -> None:
        self._document.cardChanged.disconnect(self._on_card_changed)
        self._document.cardRemoved.disconnect(self._on_card_removed)
        self._document.stackChanged.disconnect(self._on_stack_changed)
        self._document.stackRemoved.disconnect(self._on_stack_removed)

    def _on_card_changed(self, card_id: str, fields: frozenset[str]) -> None:
        if card_id not in self._tile_order:
            return
        if "stack_id" in fields:
            self._rebuild_tiles()
            return
        tile = self._tiles.get(card_id)
        if tile is not None:
            tile.refresh()

    def _on_card_removed(self, card_id: str) -> None:
        if card_id in self._tile_order:
            self._rebuild_tiles()

    def _on_stack_changed(self, stack_id: str, fields: frozenset[str]) -> None:
        if stack_id == self._stack_id and "card_ids" in fields:
            self._rebuild_tiles()

    def _on_stack_removed(self, stack_id: str) -> None:
        if stack_id == self._stack_id:
            self.dismiss()
