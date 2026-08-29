from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from indexcards.models.theme import Slot, Theme
from indexcards.utils.contrast import auto_text_color
from indexcards.utils.ids import new_slot_id

_SWATCH_SIZE = (28, 22)
_CUSTOM_TEXT_COLOR_DATA = "custom"


class ThemeSlotRowWidget(QWidget):
    """One editable row: swatch + label + optional text-color override +
    Remove. An orphaned slot shows a small "(orphaned)" marker next to its
    label but is otherwise fully editable — clearing the orphaned flag
    itself only ever happens through the dedicated resolution flow."""

    def __init__(self, slot: Slot, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.slot_id = slot.id
        self.orphaned = slot.orphaned
        self._hex = slot.hex
        self._text_color = slot.text_color

        self.swatch_button = QPushButton(self)
        self.swatch_button.setFixedSize(*_SWATCH_SIZE)
        self.swatch_button.clicked.connect(self._pick_hex)

        self.label_edit = QLineEdit(slot.label, self)

        self.text_color_combo = QComboBox(self)
        self.text_color_combo.addItem("Auto Text Color", None)
        self.text_color_combo.addItem("Custom Text Color…", _CUSTOM_TEXT_COLOR_DATA)
        self.text_color_combo.setCurrentIndex(1 if slot.text_color is not None else 0)
        self.text_color_combo.currentIndexChanged.connect(self._on_text_color_mode_changed)

        self.text_color_swatch_button = QPushButton(self)
        self.text_color_swatch_button.setFixedSize(*_SWATCH_SIZE)
        self.text_color_swatch_button.clicked.connect(self._pick_text_color)

        self.remove_button = QPushButton("Remove", self)

        layout = QHBoxLayout(self)
        layout.addWidget(self.swatch_button)
        layout.addWidget(self.label_edit, 1)
        if slot.orphaned:
            orphan_label = QLabel("(orphaned)", self)
            orphan_label.setStyleSheet("color: gray; font-style: italic;")
            layout.addWidget(orphan_label)
        layout.addWidget(self.text_color_combo)
        layout.addWidget(self.text_color_swatch_button)
        layout.addWidget(self.remove_button)

        self._refresh_swatches()

    def _refresh_swatches(self) -> None:
        self.swatch_button.setStyleSheet(f"background-color: {self._hex};")
        text_hex = self._text_color or auto_text_color(self._hex)
        self.text_color_swatch_button.setStyleSheet(f"background-color: {text_hex};")
        self.text_color_swatch_button.setVisible(
            self.text_color_combo.currentData() == _CUSTOM_TEXT_COLOR_DATA
        )

    def _pick_hex(self) -> None:
        chosen = QColorDialog.getColor(QColor(self._hex), self, "Slot Color")
        if not chosen.isValid():
            return
        self._hex = chosen.name()
        self._refresh_swatches()

    def _pick_text_color(self) -> None:
        current = self._text_color or auto_text_color(self._hex)
        chosen = QColorDialog.getColor(QColor(current), self, "Text Color")
        if not chosen.isValid():
            return
        self._text_color = chosen.name()
        self._refresh_swatches()

    def _on_text_color_mode_changed(self) -> None:
        if self.text_color_combo.currentData() != _CUSTOM_TEXT_COLOR_DATA:
            self._text_color = None
        elif self._text_color is None:
            self._text_color = auto_text_color(self._hex)
        self._refresh_swatches()

    def to_slot(self) -> Slot:
        return Slot(
            id=self.slot_id,
            label=self.label_edit.text().strip(),
            hex=self._hex,
            text_color=self._text_color,
            orphaned=self.orphaned,
        )


class ThemeEditorDialog(QDialog):
    """Edits a Theme's background color and its arbitrary-length slot
    list: add/remove/reorder (drag, via the list's own internal-move
    support) plus per-slot color/label/text-color. Doesn't change the
    theme's own id/name/origin — those are decided elsewhere (Duplicate,
    the theme picker)."""

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Edit Theme: {theme.name}")
        self._theme_id = theme.id
        self._theme_name = theme.name
        self._theme_origin = theme.origin
        self._background_color = theme.background_color

        self.slot_list = QListWidget(self)
        self.slot_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        for slot in theme.slots:
            self._add_row(slot)

        self.add_slot_button = QPushButton("Add Slot", self)
        self.add_slot_button.clicked.connect(self._on_add_slot)

        self.background_swatch_button = QPushButton(self)
        self.background_swatch_button.setFixedSize(*_SWATCH_SIZE)
        self.background_swatch_button.clicked.connect(self._pick_background_color)
        self._refresh_background_swatch()

        toolbar_row = QHBoxLayout()
        toolbar_row.addWidget(self.add_slot_button)
        toolbar_row.addStretch()
        toolbar_row.addWidget(QLabel("Background:", self))
        toolbar_row.addWidget(self.background_swatch_button)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(toolbar_row)
        layout.addWidget(self.slot_list)
        layout.addWidget(button_box)

    def _row_widget(self, index: int) -> ThemeSlotRowWidget:
        return self.slot_list.itemWidget(self.slot_list.item(index))

    def _add_row(self, slot: Slot) -> None:
        item = QListWidgetItem(self.slot_list)
        row_widget = ThemeSlotRowWidget(slot, self)
        row_widget.remove_button.clicked.connect(lambda: self._on_remove_row(item))
        self.slot_list.addItem(item)
        self.slot_list.setItemWidget(item, row_widget)
        item.setSizeHint(row_widget.sizeHint())

    def _on_remove_row(self, item: QListWidgetItem) -> None:
        self.slot_list.takeItem(self.slot_list.row(item))

    def _on_add_slot(self) -> None:
        existing_ids = {self._row_widget(i).slot_id for i in range(self.slot_list.count())}
        self._add_row(Slot(id=new_slot_id(existing_ids), label="New Color", hex="#CCCCCC"))

    def _refresh_background_swatch(self) -> None:
        self.background_swatch_button.setStyleSheet(
            f"background-color: {self._background_color};"
        )

    def _pick_background_color(self) -> None:
        chosen = QColorDialog.getColor(
            QColor(self._background_color), self, "Theme Background Color"
        )
        if not chosen.isValid():
            return
        self._background_color = chosen.name()
        self._refresh_background_swatch()

    def result_theme(self) -> Theme:
        slots = [self._row_widget(i).to_slot() for i in range(self.slot_list.count())]
        return Theme(
            id=self._theme_id,
            name=self._theme_name,
            origin=self._theme_origin,
            background_color=self._background_color,
            slots=slots,
        )
