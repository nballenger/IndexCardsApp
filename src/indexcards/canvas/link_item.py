from __future__ import annotations

from PySide6.QtCore import QLineF, Qt
from PySide6.QtGui import QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsLineItem

from indexcards.canvas.card_item import CardItem

_LINE_WIDTH = 2


class LinkItem(QGraphicsLineItem):
    """A line between two CardItems, kept current as either one moves."""

    def __init__(self, link_id: str, source_item: CardItem, target_item: CardItem) -> None:
        super().__init__()
        self.link_id = link_id
        self.source_item = source_item
        self.target_item = target_item
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setPen(QPen(Qt.GlobalColor.darkGray, _LINE_WIDTH))
        self.setZValue(-1)

        source_item.add_position_listener(self._update_line)
        target_item.add_position_listener(self._update_line)
        self._update_line()

    def disconnect_listeners(self) -> None:
        self.source_item.remove_position_listener(self._update_line)
        self.target_item.remove_position_listener(self._update_line)

    def _update_line(self) -> None:
        source_center = self.source_item.pos() + self.source_item.boundingRect().center()
        target_center = self.target_item.pos() + self.target_item.boundingRect().center()
        self.setLine(QLineF(source_center, target_center))
