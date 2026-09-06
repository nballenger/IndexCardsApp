from __future__ import annotations

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QVBoxLayout,
)

from indexcards.app_settings import (
    DEFAULT_ARRANGE_COLUMN_LIMIT,
    DEFAULT_VIEW_ON_OPEN,
    GATHER_STACKS_EDGE_OPTIONS,
    MIN_ARRANGE_COLUMN_LIMIT,
    VIEW_ON_OPEN_OPTIONS,
)
from indexcards.models.theme import Theme


class SettingsDialog(QDialog):
    """Application-level preferences: whether to warn before deleting
    cards, the theme new documents start with, whether auto-arrange's
    column layouts cap how many cards stack in a column before
    overflowing into a new one, which canvas edge Gather Stacks collects
    stacks toward, and how an existing document's canvas view is set up
    when it's opened."""

    def __init__(
        self,
        warn_before_delete: bool,
        default_theme_id: str,
        available_themes: list[Theme],
        limit_arrange_columns: bool,
        arrange_column_limit: int,
        gather_stacks_edge: str,
        view_on_open: str,
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

        self.gather_stacks_edge_combo = QComboBox(self)
        for value, label in GATHER_STACKS_EDGE_OPTIONS:
            self.gather_stacks_edge_combo.addItem(label, value)
        position = self.gather_stacks_edge_combo.findData(gather_stacks_edge)
        self.gather_stacks_edge_combo.setCurrentIndex(position if position >= 0 else 0)

        self._view_on_open_radios: dict[str, QRadioButton] = {}
        view_on_open_group = QButtonGroup(self)
        for value, label in VIEW_ON_OPEN_OPTIONS:
            radio = QRadioButton(label, self)
            radio.setChecked(value == view_on_open)
            view_on_open_group.addButton(radio)
            self._view_on_open_radios[value] = radio

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

        gather_stacks_row = QHBoxLayout()
        gather_stacks_row.addWidget(QLabel("Gather Stacks to:", self))
        gather_stacks_row.addWidget(self.gather_stacks_edge_combo)
        gather_stacks_row.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(self.warn_before_delete_checkbox)
        layout.addLayout(theme_row)
        layout.addLayout(column_limit_row)
        layout.addLayout(gather_stacks_row)
        layout.addWidget(QLabel("Document view on file open:", self))
        for value, _label in VIEW_ON_OPEN_OPTIONS:
            layout.addWidget(self._view_on_open_radios[value])
        layout.addWidget(button_box)

    def warn_before_delete(self) -> bool:
        return self.warn_before_delete_checkbox.isChecked()

    def default_theme_id(self) -> str:
        return self.default_theme_combo.currentData()

    def limit_arrange_columns(self) -> bool:
        return self.limit_arrange_columns_checkbox.isChecked()

    def arrange_column_limit(self) -> int:
        return int(self.arrange_column_limit_edit.text())

    def gather_stacks_edge(self) -> str:
        return self.gather_stacks_edge_combo.currentData()

    def view_on_open(self) -> str:
        for value, radio in self._view_on_open_radios.items():
            if radio.isChecked():
                return value
        return DEFAULT_VIEW_ON_OPEN

    def accept(self) -> None:
        if self.limit_arrange_columns_checkbox.isChecked():
            text = self.arrange_column_limit_edit.text().strip()
            if not text.isdigit() or int(text) < MIN_ARRANGE_COLUMN_LIMIT:
                self.arrange_column_limit_edit.setText(str(DEFAULT_ARRANGE_COLUMN_LIMIT))
        super().accept()
