from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from indexcards.app_settings import DEFAULT_ARRANGE_COLUMN_LIMIT, MIN_ARRANGE_COLUMN_LIMIT


class SettingsDialog(QDialog):
    """Application-level preferences: whether to warn before deleting
    cards, the background color new documents start with, and whether
    auto-arrange's column layouts cap how many cards stack in a column
    before overflowing into a new one."""

    def __init__(
        self,
        warn_before_delete: bool,
        default_background_color: str,
        limit_arrange_columns: bool,
        arrange_column_limit: int,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")

        self.warn_before_delete_checkbox = QCheckBox("Warn before deleting cards?", self)
        self.warn_before_delete_checkbox.setChecked(warn_before_delete)

        self._background_color = default_background_color
        self.background_color_button = QPushButton(self)
        self.background_color_button.clicked.connect(self._pick_color)
        self._update_color_button()

        self.limit_arrange_columns_checkbox = QCheckBox(
            "Limit number of cards in auto-arrange columns?", self
        )
        self.limit_arrange_columns_checkbox.setChecked(limit_arrange_columns)
        self.arrange_column_limit_edit = QLineEdit(str(arrange_column_limit), self)
        self.arrange_column_limit_edit.setEnabled(limit_arrange_columns)
        self.limit_arrange_columns_checkbox.toggled.connect(
            self.arrange_column_limit_edit.setEnabled
        )

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        color_row = QHBoxLayout()
        color_row.addWidget(QLabel("Default Background Color:", self))
        color_row.addWidget(self.background_color_button)
        color_row.addStretch()

        column_limit_row = QHBoxLayout()
        column_limit_row.addWidget(self.limit_arrange_columns_checkbox)
        column_limit_row.addWidget(self.arrange_column_limit_edit)
        column_limit_row.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(self.warn_before_delete_checkbox)
        layout.addLayout(color_row)
        layout.addLayout(column_limit_row)
        layout.addWidget(button_box)

    def _update_color_button(self) -> None:
        self.background_color_button.setText(self._background_color)
        self.background_color_button.setStyleSheet(
            f"background-color: {self._background_color};"
        )

    def _pick_color(self) -> None:
        chosen = QColorDialog.getColor(
            QColor(self._background_color), self, "Default Background Color"
        )
        if not chosen.isValid():
            return
        self._background_color = chosen.name()
        self._update_color_button()

    def warn_before_delete(self) -> bool:
        return self.warn_before_delete_checkbox.isChecked()

    def default_background_color(self) -> str:
        return self._background_color

    def limit_arrange_columns(self) -> bool:
        return self.limit_arrange_columns_checkbox.isChecked()

    def arrange_column_limit(self) -> int:
        return int(self.arrange_column_limit_edit.text())

    def accept(self) -> None:
        if self.limit_arrange_columns_checkbox.isChecked():
            text = self.arrange_column_limit_edit.text().strip()
            if not text.isdigit() or int(text) < MIN_ARRANGE_COLUMN_LIMIT:
                self.arrange_column_limit_edit.setText(str(DEFAULT_ARRANGE_COLUMN_LIMIT))
        super().accept()
