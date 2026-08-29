from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from indexcards.models.document import Document
from indexcards.models.theme import Slot
from indexcards.utils.color_icons import swatch_icon

_SWATCH_ICON_SIZE = QSize(20, 16)


class OrphanResolutionRowWidget(QWidget):
    """One orphaned slot: a hatched swatch + label, and an independent
    Keep/Reassign choice — defaulting to Keep, the non-destructive
    option. The target-slot combo (existing non-orphaned slots only) is
    only enabled, and only required, when Reassign is chosen."""

    def __init__(
        self,
        document: Document,
        slot: Slot,
        on_state_changed: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.slot_id = slot.id
        self._on_state_changed = on_state_changed

        swatch = QLabel(self)
        icon = swatch_icon(slot.hex, orphaned=True, size=20)
        swatch.setPixmap(icon.pixmap(_SWATCH_ICON_SIZE))

        self.keep_radio = QRadioButton("Keep", self)
        self.keep_radio.setChecked(True)
        self.reassign_radio = QRadioButton("Reassign to:", self)
        button_group = QButtonGroup(self)
        button_group.addButton(self.keep_radio)
        button_group.addButton(self.reassign_radio)
        self.keep_radio.toggled.connect(self._on_toggled)

        self.target_combo = QComboBox(self)
        for other in document.theme.slots:
            if other.orphaned or other.id == slot.id:
                continue
            self.target_combo.addItem(other.label, other.id)
        self.target_combo.setEnabled(False)
        self.target_combo.currentIndexChanged.connect(lambda _: self._on_state_changed())

        layout = QHBoxLayout(self)
        layout.addWidget(swatch)
        layout.addWidget(QLabel(slot.label, self), 1)
        layout.addWidget(self.keep_radio)
        layout.addWidget(self.reassign_radio)
        layout.addWidget(self.target_combo)

    def _on_toggled(self) -> None:
        self.target_combo.setEnabled(self.reassign_radio.isChecked())
        self._on_state_changed()

    def resolution(self) -> tuple[str, str | None]:
        if self.reassign_radio.isChecked():
            return self.slot_id, self.target_combo.currentData()
        return self.slot_id, None

    def is_valid(self) -> bool:
        if self.reassign_radio.isChecked():
            return self.target_combo.currentData() is not None
        return True


class OrphanResolutionDialog(QDialog):
    """One row per orphaned slot in orphan_slot_ids, each resolved
    independently — this is deliberately not a single global choice, so
    e.g. one orphan can be kept while another is merged into an existing
    color. OK is only enabled once every row currently set to Reassign
    has a target chosen; rows left on Keep never block it."""

    def __init__(
        self, document: Document, orphan_slot_ids: list[str], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Resolve Orphaned Colors")
        self._rows: list[OrphanResolutionRowWidget] = [
            OrphanResolutionRowWidget(
                document, document.get_slot(slot_id), self._update_ok_enabled, self
            )
            for slot_id in orphan_slot_ids
        ]

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        for row in self._rows:
            layout.addWidget(row)
        layout.addWidget(self.button_box)

        self._update_ok_enabled()

    def _update_ok_enabled(self) -> None:
        ok_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        ok_button.setEnabled(all(row.is_valid() for row in self._rows))

    def resolutions(self) -> list[tuple[str, str | None]]:
        return [row.resolution() for row in self._rows]
