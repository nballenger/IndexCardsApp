from __future__ import annotations

from PySide6.QtCore import QLineF, QObject, Qt, Signal
from PySide6.QtGui import QMouseEvent, QPen
from PySide6.QtWidgets import QGraphicsLineItem

from indexcards.canvas.card_item import CardItem


class LinkDrawController(QObject):
    """Click-drag-to-connect interaction, active only while Link Mode is on.

    While active, a press on a card starts a temporary line following the
    cursor; releasing over a different card emits linkRequested (the caller
    owns pushing the actual AddLinkCommand) and releasing anywhere else
    cancels. Inactive, mouse_press/move/release all return False so the
    view's normal click/drag handling (selection, card move) proceeds.
    """

    linkRequested = Signal(str, str)  # source_card_id, target_card_id

    def __init__(self, view, parent=None) -> None:
        super().__init__(parent)
        self._view = view
        self.active = False
        self._source_card_id: str | None = None
        self._temp_line: QGraphicsLineItem | None = None

    def set_active(self, active: bool) -> None:
        self.active = active
        if not active:
            self._cancel()
        scene = self._view.scene()
        if scene is not None and hasattr(scene, "set_link_mode_active"):
            scene.set_link_mode_active(active)

    def mouse_press(self, event: QMouseEvent) -> bool:
        if not self.active:
            return False
        scene_pos = self._view.mapToScene(event.position().toPoint())
        item = self._card_item_at(scene_pos)
        if item is None:
            return False
        self._source_card_id = item.card_id
        self._temp_line = QGraphicsLineItem(QLineF(scene_pos, scene_pos))
        self._temp_line.setPen(QPen(Qt.GlobalColor.gray, 2, Qt.PenStyle.DashLine))
        self._view.scene().addItem(self._temp_line)
        return True

    def mouse_move(self, event: QMouseEvent) -> bool:
        if not self.active or self._temp_line is None:
            return False
        scene_pos = self._view.mapToScene(event.position().toPoint())
        line = self._temp_line.line()
        line.setP2(scene_pos)
        self._temp_line.setLine(line)
        return True

    def mouse_release(self, event: QMouseEvent) -> bool:
        if not self.active or self._temp_line is None:
            return False
        scene_pos = self._view.mapToScene(event.position().toPoint())
        target_item = self._card_item_at(scene_pos)
        source_id = self._source_card_id
        self._cancel()
        if target_item is not None and target_item.card_id != source_id:
            self.linkRequested.emit(source_id, target_item.card_id)
        return True

    def _card_item_at(self, scene_pos) -> CardItem | None:
        scene = self._view.scene()
        if scene is None:
            return None
        for item in scene.items(scene_pos):
            if isinstance(item, CardItem):
                return item
        return None

    def _cancel(self) -> None:
        if self._temp_line is not None:
            scene = self._view.scene()
            if scene is not None:
                scene.removeItem(self._temp_line)
            self._temp_line = None
        self._source_card_id = None
