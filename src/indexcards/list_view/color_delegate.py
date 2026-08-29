from __future__ import annotations

from PySide6.QtCore import QModelIndex, QRect, QRectF, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QComboBox, QStyledItemDelegate, QStyleOptionViewItem, QWidget

from indexcards.utils.color_icons import paint_color_swatch, swatch_icon


class ColorDelegate(QStyledItemDelegate):
    def createEditor(self, parent: QWidget, option, index: QModelIndex) -> QWidget:
        combo = QComboBox(parent)
        for slot in index.model().document.theme.slots:
            if slot.orphaned:
                continue
            combo.addItem(swatch_icon(slot.hex), slot.label, slot.id)
        return combo

    def setEditorData(self, editor: QComboBox, index: QModelIndex) -> None:
        current_slot_id = index.model().data(index, Qt.ItemDataRole.EditRole)
        position = editor.findData(current_slot_id)
        editor.setCurrentIndex(position if position >= 0 else 0)

    def setModelData(self, editor: QComboBox, model, index: QModelIndex) -> None:
        new_slot_id = editor.currentData()
        if new_slot_id == index.model().data(index, Qt.ItemDataRole.EditRole):
            return
        model.setData(index, new_slot_id, Qt.ItemDataRole.EditRole)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        slot_id = index.model().data(index, Qt.ItemDataRole.EditRole)
        slot = index.model().document.get_slot(slot_id)
        painter.save()
        swatch_width = 16
        swatch = QRect(
            option.rect.left() + (option.rect.width() - swatch_width) // 2,
            option.rect.top() + 4,
            swatch_width,
            option.rect.height() - 8,
        )
        paint_color_swatch(painter, QRectF(swatch), slot.hex, orphaned=slot.orphaned)
        painter.setPen(Qt.GlobalColor.darkGray)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(swatch)
        painter.restore()
