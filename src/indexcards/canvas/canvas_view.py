from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QKeyEvent, QMouseEvent, QPainter, QWheelEvent
from PySide6.QtWidgets import QGraphicsView

from indexcards.canvas.link_draw_controller import LinkDrawController

MIN_ZOOM = 0.2
MAX_ZOOM = 4.0
WHEEL_ZOOM_STEP = 1.15


class CanvasView(QGraphicsView):
    deleteRequested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self._zoom = 1.0
        self.link_controller = LinkDrawController(self, parent=self)

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

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
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
