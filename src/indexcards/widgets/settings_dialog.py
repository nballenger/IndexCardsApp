from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


class SettingsDialog(QDialog):
    """Application-level preferences: whether to warn before deleting
    cards, and the background color new documents start with."""

    def __init__(
        self, warn_before_delete: bool, default_background_color: str, parent=None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")

        self.warn_before_delete_checkbox = QCheckBox("Warn before deleting cards?", self)
        self.warn_before_delete_checkbox.setChecked(warn_before_delete)

        self._background_color = default_background_color
        self.background_color_button = QPushButton(self)
        self.background_color_button.clicked.connect(self._pick_color)
        self._update_color_button()

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        color_row = QHBoxLayout()
        color_row.addWidget(QLabel("Default Background Color:", self))
        color_row.addWidget(self.background_color_button)
        color_row.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(self.warn_before_delete_checkbox)
        layout.addLayout(color_row)
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
