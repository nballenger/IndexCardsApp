from __future__ import annotations

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtWidgets import QLineEdit, QStyledItemDelegate, QWidget


class TagDelegate(QStyledItemDelegate):
    def createEditor(self, parent: QWidget, option, index: QModelIndex) -> QWidget:
        return QLineEdit(parent)

    def setEditorData(self, editor: QLineEdit, index: QModelIndex) -> None:
        tags = index.model().data(index, Qt.ItemDataRole.EditRole) or []
        editor.setText(", ".join(tags))

    def setModelData(self, editor: QLineEdit, model, index: QModelIndex) -> None:
        tags = [tag.strip() for tag in editor.text().split(",") if tag.strip()]
        model.setData(index, tags, Qt.ItemDataRole.EditRole)
