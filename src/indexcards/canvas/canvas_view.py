from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QContextMenuEvent,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QWheelEvent,
)
from PySide6.QtWidgets import QGraphicsTextItem, QGraphicsView, QMenu

from indexcards.canvas.link_draw_controller import LinkDrawController

MIN_ZOOM = 0.2
MAX_ZOOM = 4.0
WHEEL_ZOOM_STEP = 1.15
FIT_MARGIN = 40.0
VIEW_EXTENTS_MARGIN = 20.0  # tighter than FIT_MARGIN — a snug, deliberate "show everything"


class CanvasView(QGraphicsView):
    deleteRequested = Signal()
    cardCreated = Signal(str)
    backgroundChangeRequested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self._zoom = 1.0
        self.link_controller = LinkDrawController(self, parent=self)

    def setScene(self, scene) -> None:
        super().setScene(scene)
        if scene is not None and hasattr(scene, "set_link_mode_active"):
            # Link Mode is a per-window toggle (owned by link_controller),
            # not per-document — a newly attached scene (e.g. from opening
            # another file) needs to pick up whatever it's currently set to
            # rather than resetting card cursors to their non-Link-Mode look.
            scene.set_link_mode_active(self.link_controller.active)

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
        if self.link_controller.mouse_press(event):
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self.link_controller.mouse_move(event):
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self.link_controller.mouse_release(event):
            event.accept()
            return
        super().mouseReleaseEvent(event)

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
        menu, change_background_action = self._build_background_context_menu()
        chosen = menu.exec(event.globalPos())
        self._handle_background_context_menu_choice(chosen, change_background_action)

    def _build_background_context_menu(self) -> tuple[QMenu, QAction]:
        """Builds the menu without exec()'ing it, so tests can inspect its
        contents without triggering a real, blocking modal popup."""
        menu = QMenu(self)
        change_background_action = menu.addAction("Change Background")
        return menu, change_background_action

    def _handle_background_context_menu_choice(
        self, chosen: QAction | None, change_background_action: QAction
    ) -> None:
        """Split out from contextMenuEvent so tests can exercise the
        dispatch decision directly, without depending on QMenu.exec()'s
        real (unpatchable, blocking) return value."""
        if chosen is change_background_action:
            self.backgroundChangeRequested.emit()

    def keyPressEvent(self, event: QKeyEvent) -> None:
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
