from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QRadioButton,
    QVBoxLayout,
)

from indexcards.feature_flags import TAGS_ENABLED


class ArrangeDialog(QDialog):
    """Lets the user choose how to auto-arrange cards: by color, by
    whether they have a specific tag (when TAGS_ENABLED), tiled into a
    row/column grid (order not significant), or scattered randomly."""

    def __init__(self, available_tags: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Auto-Arrange")

        self.color_radio = QRadioButton("By Color", self)
        self.color_radio.setChecked(True)

        self.tag_radio = QRadioButton("By Tag:", self)
        self.tag_combo = QComboBox(self)
        self.tag_combo.addItems(available_tags)
        self.tag_combo.setEnabled(False)
        self.tag_radio.setEnabled(bool(available_tags))
        self.tag_radio.toggled.connect(self.tag_combo.setEnabled)

        self.tile_radio = QRadioButton("Tile", self)
        self.scatter_radio = QRadioButton("Scatter", self)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.color_radio)
        if TAGS_ENABLED:
            tag_row = QHBoxLayout()
            tag_row.addWidget(self.tag_radio)
            tag_row.addWidget(self.tag_combo)
            layout.addLayout(tag_row)
        else:
            # Parented to self but not placed in a layout, so without this
            # Qt still renders them at their default (0, 0) position,
            # overlapping color_radio instead of just staying offscreen.
            self.tag_radio.setVisible(False)
            self.tag_combo.setVisible(False)
        layout.addWidget(self.tile_radio)
        layout.addWidget(self.scatter_radio)
        layout.addWidget(button_box)

    def selected_group_by(self) -> str:
        if self.tile_radio.isChecked():
            return "tile"
        if self.scatter_radio.isChecked():
            return "scatter"
        return "tag" if TAGS_ENABLED and self.tag_radio.isChecked() else "color"

    def selected_tag(self) -> str | None:
        if not TAGS_ENABLED or not self.tag_radio.isChecked() or self.tag_combo.count() == 0:
            return None
        return self.tag_combo.currentText()
