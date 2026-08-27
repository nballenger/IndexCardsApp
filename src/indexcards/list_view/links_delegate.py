from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPoint, QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QApplication, QStyle, QStyledItemDelegate, QStyleOptionViewItem

from indexcards.list_view.card_table_model import LINKS_ROLE

_SEPARATOR = ", "
_LINK_COLOR = QColor("#0645AD")
_TEXT_MARGIN = 4  # matches Qt's default item-text left inset


class LinksDelegate(QStyledItemDelegate):
    """Paints each linked card id in the Links column as its own
    segment (blue, underlined while hovered) instead of one plain
    comma-joined string — ListViewWidget tracks which segment the
    mouse is over and drives hovered_index/hovered_segment here so a
    tooltip for just that linked card can be shown."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.hovered_index = QModelIndex()
        self.hovered_segment = -1

    def segments(
        self, option: QStyleOptionViewItem, index: QModelIndex
    ) -> list[tuple[str, str, QRect]]:
        """(card_id, card_text, rect) for each linked card, rect being
        that id's hoverable text area within the cell."""
        links = index.data(LINKS_ROLE) or []
        metrics = QFontMetrics(option.font)
        x = option.rect.left() + _TEXT_MARGIN
        result = []
        for position, (card_id, text) in enumerate(links):
            width = metrics.horizontalAdvance(card_id)
            rect = QRect(x, option.rect.top(), width, option.rect.height())
            result.append((card_id, text, rect))
            x += width
            if position < len(links) - 1:
                x += metrics.horizontalAdvance(_SEPARATOR)
        return result

    def segment_at(self, option: QStyleOptionViewItem, index: QModelIndex, pos: QPoint) -> int:
        for position, (_card_id, _text, rect) in enumerate(self.segments(option, index)):
            if rect.contains(pos):
                return position
        return -1

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        painter.save()
        blank = QStyleOptionViewItem(option)
        blank.text = ""
        style = option.widget.style() if option.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, blank, painter, option.widget)

        segments = self.segments(option, index)
        hovered_segment = self.hovered_segment if index == self.hovered_index else -1
        separator_width = QFontMetrics(option.font).horizontalAdvance(_SEPARATOR)
        for position, (card_id, _text, rect) in enumerate(segments):
            font = QFont(option.font)
            font.setUnderline(position == hovered_segment)
            painter.setFont(font)
            painter.setPen(_LINK_COLOR)
            painter.drawText(
                rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, card_id
            )
            if position < len(segments) - 1:
                painter.setFont(option.font)
                painter.setPen(option.palette.text().color())
                separator_rect = QRect(rect.right(), rect.top(), separator_width, rect.height())
                painter.drawText(
                    separator_rect,
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    _SEPARATOR,
                )
        painter.restore()
