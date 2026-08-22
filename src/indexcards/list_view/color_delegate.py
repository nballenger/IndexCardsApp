from __future__ import annotations

from PySide6.QtCore import QModelIndex, QRect, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QComboBox, QStyledItemDelegate, QStyleOptionViewItem, QWidget

from indexcards.models.palette import PALETTE


class ColorDelegate(QStyledItemDelegate):
    def createEditor(self, parent: QWidget, option, index: QModelIndex) -> QWidget:
        combo = QComboBox(parent)
        for name, hex_value in PALETTE.items():
            combo.addItem(name, hex_value)
        return combo

    def setEditorData(self, editor: QComboBox, index: QModelIndex) -> None:
        current_hex = index.model().data(index, Qt.ItemDataRole.EditRole)
        position = editor.findData(current_hex)
        editor.setCurrentIndex(position if position >= 0 else 0)

    def setModelData(self, editor: QComboBox, model, index: QModelIndex) -> None:
        model.setData(index, editor.currentData(), Qt.ItemDataRole.EditRole)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        hex_value = index.model().data(index, Qt.ItemDataRole.EditRole)
        painter.save()
        swatch_width = 16
        swatch = QRect(
            option.rect.left() + (option.rect.width() - swatch_width) // 2,
            option.rect.top() + 4,
            swatch_width,
            option.rect.height() - 8,
        )
        painter.setBrush(QColor(hex_value))
        painter.setPen(Qt.GlobalColor.darkGray)
        painter.drawRect(swatch)
        painter.restore()
