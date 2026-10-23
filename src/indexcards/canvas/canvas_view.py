from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QContextMenuEvent,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QResizeEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import QApplication, QGraphicsTextItem, QGraphicsView, QMenu

from indexcards.arrange.auto_arrange import positions_bbox
from indexcards.canvas.card_item import CardItem
from indexcards.canvas.color_key_overlay import ColorKeyOverlay
from indexcards.canvas.link_draw_controller import LinkDrawController
from indexcards.canvas.region_item import RegionItem
from indexcards.canvas.stack_item import StackItem
from indexcards.canvas.stack_overlay import StackOverlay

MIN_ZOOM = 0.2
MAX_ZOOM = 4.0
WHEEL_ZOOM_STEP = 1.15
FIT_MARGIN = 40.0
VIEW_EXTENTS_MARGIN = 20.0  # tighter than FIT_MARGIN — a snug, deliberate "show everything"
PAN_OVERSCAN_PX = 10.0  # how close to fully off-screen the content's edge may be panned

# Dragging something (or a rubber band, or a new link) into this band along a
# viewport edge pans the canvas that way; the pan speeds up from 0 at the
# band's inner edge to EDGE_PAN_SPEED px per tick at the edge itself, and up
# to EDGE_PAN_MAX_FACTOR times that when the pointer is dragged past it.
EDGE_PAN_MARGIN = 40.0
EDGE_PAN_SPEED = 12.0
EDGE_PAN_MAX_FACTOR = 2.0
EDGE_PAN_INTERVAL_MS = 16


def _edge_scroll_speed(coord: float, size: float) -> int:
    """Signed scroll step (px) for a pointer at `coord` along an axis of
    length `size`: negative toward the low (left/top) edge, positive toward
    the high one, 0 in the interior."""
    if coord < EDGE_PAN_MARGIN:
        depth, sign = EDGE_PAN_MARGIN - coord, -1
    elif coord > size - EDGE_PAN_MARGIN:
        depth, sign = coord - (size - EDGE_PAN_MARGIN), 1
    else:
        return 0
    factor = min(depth / EDGE_PAN_MARGIN, EDGE_PAN_MAX_FACTOR)
    return sign * max(1, round(factor * EDGE_PAN_SPEED))


class CanvasView(QGraphicsView):
    deleteRequested = Signal()
    cardCreated = Signal(str)
    backgroundChangeRequested = Signal()
    # "New Region Here" at a scene point -- MainWindow owns the label prompt
    # (same split as CanvasScene.regionFromSelectionRequested), so the view
    # just relays where.
    newRegionRequested = Signal(float, float)

    def __init__(
        self, parent=None, get_minimum_font_size: Callable[[], int] | None = None
    ) -> None:
        super().__init__(parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self._zoom = 1.0
        self._autoscroll_press_pos: QPoint | None = None
        self._autoscroll_last_pos: QPoint | None = None
        self._autoscroll_timer = QTimer(self)
        self._autoscroll_timer.setInterval(EDGE_PAN_INTERVAL_MS)
        self._autoscroll_timer.timeout.connect(self._autoscroll_tick)
        self.link_controller = LinkDrawController(self, parent=self)
        self.color_key_overlay = ColorKeyOverlay(self.viewport())
        self.stack_overlay = StackOverlay(
            self.viewport(), get_minimum_font_size=get_minimum_font_size
        )

    def setScene(self, scene) -> None:
        old_scene = self.scene()
        if old_scene is not None and hasattr(old_scene, "contentBoundsChanged"):
            old_scene.contentBoundsChanged.disconnect(self._update_scene_rect)
        super().setScene(scene)
        if scene is not None and hasattr(scene, "set_link_mode_active"):
            # Link Mode is a per-window toggle (owned by link_controller),
            # not per-document — a newly attached scene (e.g. from opening
            # another file) needs to pick up whatever it's currently set to
            # rather than resetting card cursors to their non-Link-Mode look.
            scene.set_link_mode_active(self.link_controller.active)
        if scene is not None and hasattr(scene, "contentBoundsChanged"):
            scene.contentBoundsChanged.connect(self._update_scene_rect)
        self.color_key_overlay.set_document(getattr(scene, "document", None))
        self.stack_overlay.set_document(getattr(scene, "document", None))
        self._update_scene_rect()

    @property
    def zoom(self) -> float:
        return self._zoom

    def zoom_by(self, factor: float) -> None:
        target_zoom = max(MIN_ZOOM, min(MAX_ZOOM, self._zoom * factor))
        applied_factor = target_zoom / self._zoom
        if applied_factor == 1.0:
            return
        self.scale(applied_factor, applied_factor)
        self._zoom = target_zoom
        self._update_scene_rect()

    def fit_to_content(self, margin: float = FIT_MARGIN) -> None:
        """Zooms/pans so every item in the scene is visible at once."""
        scene = self.scene()
        if scene is None:
            return
        bounds = scene.itemsBoundingRect()
        if bounds.isEmpty():
            return
        bounds = bounds.adjusted(-margin, -margin, margin, margin)
        self.fitInView(bounds, Qt.AspectRatioMode.KeepAspectRatio)
        # fitInView sets the transform directly rather than going through
        # zoom_by, so resync our tracked zoom to match reality; later
        # zoom_by calls are relative to this and will re-clamp naturally.
        self._zoom = self.transform().m11()
        self._update_scene_rect()

    def center_or_fit_to_content(self, margin: float = VIEW_EXTENTS_MARGIN) -> None:
        """"All objects / Zoom Extents" document-open behavior: if
        everything fits within the viewport at native (1:1) resolution,
        resets to that zoom and centers the content -- never magnifies a
        sparse board just to fill the window. Otherwise zooms out (never
        in) just enough to fit everything, same as fit_to_content."""
        scene = self.scene()
        if scene is None:
            return
        bounds = scene.itemsBoundingRect()
        if bounds.isEmpty():
            return
        bounds = bounds.adjusted(-margin, -margin, margin, margin)
        if bounds.width() <= 0 or bounds.height() <= 0:
            return
        viewport_size = self.viewport().size()
        required_scale = min(
            viewport_size.width() / bounds.width(), viewport_size.height() / bounds.height()
        )
        if required_scale >= 1.0:
            self.resetTransform()
            self._zoom = 1.0
            self.centerOn(bounds.center())
        else:
            self.fitInView(bounds, Qt.AspectRatioMode.KeepAspectRatio)
            self._zoom = self.transform().m11()
        self._update_scene_rect()

    def restore_view_state(self, zoom: float, center_x: float, center_y: float) -> None:
        """"View from last save" document-open behavior: reproduces a
        previously captured zoom/pan exactly -- deliberately not clamped
        to MIN_ZOOM/MAX_ZOOM, since exact reproduction is the point (a
        saved zoom from an earlier fit_to_content on very large content
        can legitimately sit outside that range already)."""
        self.resetTransform()
        self.scale(zoom, zoom)
        self._zoom = zoom
        self.centerOn(QPointF(center_x, center_y))
        self._update_scene_rect()

    def fit_to_positions(
        self, positions: dict[str, tuple[float, float]], margin: float = FIT_MARGIN
    ) -> None:
        """Zooms/pans so every position in `positions` (e.g. the fresh
        layout an Explode just produced) is visible, plus the normal
        margin — used instead of fit_to_content when the relevant content
        is a specific subset of the scene rather than everything in it."""
        if not positions:
            return
        min_x, min_y, max_x, max_y = positions_bbox(positions)
        bounds = QRectF(min_x, min_y, max_x - min_x, max_y - min_y)
        bounds = bounds.adjusted(-margin, -margin, margin, margin)
        self.fitInView(bounds, Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom = self.transform().m11()
        self._update_scene_rect()

    def _update_scene_rect(self) -> None:
        """Widens the scene's pannable area beyond the tight
        itemsBoundingRect() Qt would otherwise derive automatically, so the
        user can pan until the content's outermost edge is PAN_OVERSCAN_PX
        from sliding fully off the viewport in every direction — not just
        until that edge reaches the viewport's edge. The margin is sized in
        scene units from the current viewport size and zoom (bigger
        viewport or more zoomed out ⇒ more scene-unit margin needed for the
        same on-screen overscan), so it's recomputed on every resize, zoom
        change, and content change (see contentBoundsChanged) rather than
        set once.

        No special-casing for an empty scene (bounds.isEmpty()): resetting
        to a null QRectF to fall back on Qt's own auto-derived sceneRect
        would seem like the obvious way to handle "nothing to pan around,"
        but that auto-derived rect is a high-water mark Qt tracks
        internally from items' bounds growing — it does not shrink back
        down when items are removed, so it can silently disagree with
        bounds here (stale, arbitrary-looking values from whatever the
        scene's content used to be). Just running every scene through the
        same adjusted-bounds math — including a zero-size `bounds` at the
        origin when there are no items — sidesteps that quirk entirely and
        keeps this function's output a pure function of (bounds, viewport,
        zoom).

        This lands close to, but not exactly at, PAN_OVERSCAN_PX: Qt's own
        scrollbar-range calculation from sceneRect folds in a little extra
        (frame width, scrollbar geometry) this doesn't try to reproduce
        exactly, so the real overscan ends up roughly a scrollbar's width
        less than PAN_OVERSCAN_PX — measured at ~15-20px short on this
        platform/style, i.e. the content can go just fully off-screen
        rather than stopping with a sliver still showing. That's fine for
        what this is — "way more pan room than the old zero-slack
        behavior, stopping close to the edge" — not a pixel-exact
        guarantee, and not worth chasing further given how platform- and
        style-dependent scrollbar geometry is."""
        scene = self.scene()
        if scene is None:
            return
        bounds = scene.itemsBoundingRect()
        viewport_size = self.viewport().size()
        margin_x = max(0.0, viewport_size.width() - PAN_OVERSCAN_PX) / self._zoom
        margin_y = max(0.0, viewport_size.height() - PAN_OVERSCAN_PX) / self._zoom
        scene.setSceneRect(bounds.adjusted(-margin_x, -margin_y, margin_x, margin_y))

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_scene_rect()
        self.color_key_overlay.reposition(self.viewport().size())
        self.stack_overlay.reposition(self.viewport().size())

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        # QAbstractScrollArea's default scrollContentsBy -- which
        # QGraphicsView doesn't override -- fast-scrolls by calling
        # viewport().scroll(dx, dy), and QWidget.scroll() moves EVERY
        # child of that widget along with it, not just the painted scene
        # content. color_key_overlay/stack_overlay are plain QWidget
        # children of the viewport (so they draw on top of the scene
        # without being scene items themselves), so a pan silently drags
        # them along with the cards unless they're snapped back to their
        # own corner-anchored spot right after.
        super().scrollContentsBy(dx, dy)
        self.color_key_overlay.reposition(self.viewport().size())
        self.stack_overlay.reposition(self.viewport().size())

    def ensure_content_visible(self, margin: float = FIT_MARGIN) -> None:
        """Makes sure every item is visible, adjusting the viewport as
        little as possible: does nothing if everything's already in view,
        pans (without zooming) if the content already fits at the current
        zoom but is simply scrolled out of view, and only falls back to
        fit_to_content's zoom-to-extents when the content is too big for
        the current viewport to show at any pan position."""
        scene = self.scene()
        if scene is None:
            return
        bounds = scene.itemsBoundingRect()
        if bounds.isEmpty():
            return
        bounds = bounds.adjusted(-margin, -margin, margin, margin)

        visible_rect = self.mapToScene(self.viewport().rect()).boundingRect()
        if visible_rect.contains(bounds):
            return

        if bounds.width() <= visible_rect.width() and bounds.height() <= visible_rect.height():
            self.centerOn(bounds.center())
            return

        self.fit_to_content(margin)

    def wheelEvent(self, event: QWheelEvent) -> None:
        # Qt maps ControlModifier to the physical Cmd key on macOS (and Meta to
        # physical Control), so this is Cmd+scroll on Mac. That's deliberate,
        # not a platform quirk to work around: physical Ctrl+scroll is already
        # claimed by macOS's own Accessibility zoom, and Cmd+scroll matches the
        # zoom convention several Mac apps already use.
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = WHEEL_ZOOM_STEP if event.angleDelta().y() > 0 else 1 / WHEEL_ZOOM_STEP
            self.zoom_by(factor)
            event.accept()
            return
        super().wheelEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._autoscroll_press_pos = event.position().toPoint()
            self._autoscroll_last_pos = self._autoscroll_press_pos
        if self.link_controller.mouse_press(event):
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self._autoscroll_last_pos = event.position().toPoint()
        if self.link_controller.mouse_move(event):
            event.accept()
        else:
            super().mouseMoveEvent(event)
        self._update_autoscroll()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._stop_autoscroll()
        if self.link_controller.mouse_release(event):
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # -- edge pan: scroll while something is dragged against the viewport edge --

    def _left_button_down(self) -> bool:
        return bool(QApplication.mouseButtons() & Qt.MouseButton.LeftButton)

    def _drag_in_progress(self) -> bool:
        """An item drag/resize, a link being drawn, or a rubber-band
        selection -- past the click-vs-drag threshold. Not in-place text
        editing (the grabber is the card's child text item) and not while a
        Stack overlay is open (its tiles drag in the overlay's own view)."""
        press, last = self._autoscroll_press_pos, self._autoscroll_last_pos
        scene = self.scene()
        if press is None or last is None or scene is None or self.stack_overlay.is_open:
            return False
        if (last - press).manhattanLength() < QApplication.startDragDistance():
            return False
        if self.link_controller.is_drawing:
            return True
        grabber = scene.mouseGrabberItem()
        if grabber is None:
            return self.dragMode() == QGraphicsView.DragMode.RubberBandDrag
        return isinstance(grabber, (CardItem, StackItem, RegionItem))

    def _update_autoscroll(self) -> None:
        if self._drag_in_progress():
            if not self._autoscroll_timer.isActive():
                self._autoscroll_timer.start()
        else:
            self._autoscroll_timer.stop()

    def _stop_autoscroll(self) -> None:
        self._autoscroll_timer.stop()
        self._autoscroll_press_pos = None
        self._autoscroll_last_pos = None

    def _autoscroll_tick(self) -> None:
        if not self._left_button_down() or not self._drag_in_progress():
            self._stop_autoscroll()
            return
        pos = self._autoscroll_last_pos
        viewport = self.viewport()
        dx = _edge_scroll_speed(pos.x(), viewport.width())
        dy = _edge_scroll_speed(pos.y(), viewport.height())
        if dx == 0 and dy == 0:
            return
        hbar, vbar = self.horizontalScrollBar(), self.verticalScrollBar()
        before = (hbar.value(), vbar.value())
        hbar.setValue(before[0] + dx)
        vbar.setValue(before[1] + dy)
        if (hbar.value(), vbar.value()) == before:
            return  # already at the end of the scrollable area
        # The pointer hasn't moved but the scene under it has: re-deliver it
        # so whatever is being dragged (or the rubber band, or the link's
        # free end) follows -- Qt tracks the last move in scene coordinates,
        # so the item advances by exactly the distance scrolled.
        follow = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(pos),
            viewport.mapToGlobal(QPointF(pos)),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(viewport, follow)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        scene = self.scene()
        if scene is None or self.link_controller.active:
            super().mouseDoubleClickEvent(event)
            return
        scene_pos = self.mapToScene(event.position().toPoint())
        if scene.itemAt(scene_pos, self.transform()) is not None:
            super().mouseDoubleClickEvent(event)
            return
        card_id = scene.add_card_at(scene_pos.x(), scene_pos.y())
        if card_id is not None:
            self.cardCreated.emit(card_id)
        event.accept()

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        scene = self.scene()
        if scene is None:
            super().contextMenuEvent(event)
            return
        scene_pos = self.mapToScene(event.pos())
        if scene.itemAt(scene_pos, self.transform()) is not None:
            # Let the item under the cursor (e.g. a card) show its own
            # context menu instead of this background one.
            super().contextMenuEvent(event)
            return
        menu, change_background_action, new_region_action = self._build_background_context_menu()
        chosen = menu.exec(event.globalPos())
        self._handle_background_context_menu_choice(
            chosen, change_background_action, new_region_action, scene_pos
        )

    def _build_background_context_menu(self) -> tuple[QMenu, QAction, QAction]:
        """Builds the menu without exec()'ing it, so tests can inspect its
        contents without triggering a real, blocking modal popup."""
        menu = QMenu(self)
        change_background_action = menu.addAction("Change Background")
        new_region_action = menu.addAction("New Region Here")
        return menu, change_background_action, new_region_action

    def _handle_background_context_menu_choice(
        self,
        chosen: QAction | None,
        change_background_action: QAction,
        new_region_action: QAction,
        scene_pos: QPointF,
    ) -> None:
        """Split out from contextMenuEvent so tests can exercise the
        dispatch decision directly, without depending on QMenu.exec()'s
        real (unpatchable, blocking) return value."""
        if chosen is change_background_action:
            self.backgroundChangeRequested.emit()
        elif chosen is new_region_action:
            self.newRegionRequested.emit(scene_pos.x(), scene_pos.y())

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape and self.stack_overlay.is_open:
            # Cheap defense-in-depth against Qt focus-timing edge cases —
            # normally the overlay's own grid view holds focus and handles
            # Escape itself.
            self.stack_overlay.dismiss()
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            scene = self.scene()
            if scene is not None and isinstance(scene.focusItem(), QGraphicsTextItem):
                # A card is being edited in place — let Delete/Backspace
                # delete a character instead of the whole card.
                super().keyPressEvent(event)
                return
            self.deleteRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def viewportEvent(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.NativeGesture:
            # A trackpad pinch is captured by the OS/Qt directly on the
            # viewport's native view, bypassing normal Qt child-widget
            # event routing entirely — unlike a mouse press or wheel
            # scroll, it never gets a chance to reach StackOverlay first
            # and be swallowed there, even though the overlay visually
            # covers the whole viewport. Has to be blocked here instead.
            if self.stack_overlay.is_open:
                return True
            gesture_type = getattr(event, "gestureType", None)
            value = getattr(event, "value", None)
            if callable(gesture_type) and callable(value):
                try:
                    if gesture_type() == Qt.NativeGestureType.ZoomNativeGesture:
                        self.zoom_by(1.0 + value())
                        return True
                except AttributeError:
                    pass
        return super().viewportEvent(event)
