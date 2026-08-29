from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from indexcards.app_settings import DEFAULT_ARRANGE_COLUMN_LIMIT, MIN_ARRANGE_COLUMN_LIMIT
from indexcards.models.theme import Theme


class SettingsDialog(QDialog):
    """Application-level preferences: whether to warn before deleting
    cards, the theme new documents start with, and whether auto-arrange's
    column layouts cap how many cards stack in a column before
    overflowing into a new one."""

    def __init__(
        self,
        warn_before_delete: bool,
        default_theme_id: str,
        available_themes: list[Theme],
        limit_arrange_columns: bool,
        arrange_column_limit: int,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")

        self.warn_before_delete_checkbox = QCheckBox("Warn before deleting cards?", self)
        self.warn_before_delete_checkbox.setChecked(warn_before_delete)

        self.default_theme_combo = QComboBox(self)
        for theme in available_themes:
            label = f"{theme.name} (preset)" if theme.origin == "preset" else theme.name
            self.default_theme_combo.addItem(label, theme.id)
        position = self.default_theme_combo.findData(default_theme_id)
        self.default_theme_combo.setCurrentIndex(position if position >= 0 else 0)

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

        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("Default Theme:", self))
        theme_row.addWidget(self.default_theme_combo)
        theme_row.addStretch()

        column_limit_row = QHBoxLayout()
        column_limit_row.addWidget(self.limit_arrange_columns_checkbox)
        column_limit_row.addWidget(self.arrange_column_limit_edit)
        column_limit_row.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(self.warn_before_delete_checkbox)
        layout.addLayout(theme_row)
        layout.addLayout(column_limit_row)
        layout.addWidget(button_box)

    def warn_before_delete(self) -> bool:
        return self.warn_before_delete_checkbox.isChecked()

    def default_theme_id(self) -> str:
        return self.default_theme_combo.currentData()

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
