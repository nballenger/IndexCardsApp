from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QRadioButton,
    QVBoxLayout,
)


class ArrangeDialog(QDialog):
    """Lets the user choose how to auto-arrange cards: by color, or by
    whether they have a specific tag."""

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

        tag_row = QHBoxLayout()
        tag_row.addWidget(self.tag_radio)
        tag_row.addWidget(self.tag_combo)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.color_radio)
        layout.addLayout(tag_row)
        layout.addWidget(button_box)

    def selected_group_by(self) -> str:
        return "tag" if self.tag_radio.isChecked() else "color"

    def selected_tag(self) -> str | None:
        if not self.tag_radio.isChecked() or self.tag_combo.count() == 0:
            return None
        return self.tag_combo.currentText()
