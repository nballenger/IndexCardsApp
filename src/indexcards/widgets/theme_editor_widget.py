from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QColorDialog,
    QComboBox,
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
from indexcards.utils.color_icons import swatch_icon
from indexcards.utils.contrast import auto_text_color
from indexcards.utils.ids import new_slot_id

_SWATCH_SIZE = (28, 22)
_SWATCH_ICON_SIZE = QSize(20, 16)
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
        self.swatch_button.setIconSize(_SWATCH_ICON_SIZE)
        self.swatch_button.clicked.connect(self._pick_hex)

        self.label_edit = QLineEdit(slot.label, self)

        self.text_color_combo = QComboBox(self)
        self.text_color_combo.addItem("Auto Text Color", None)
        self.text_color_combo.addItem("Custom Text Color…", _CUSTOM_TEXT_COLOR_DATA)
        self.text_color_combo.setCurrentIndex(1 if slot.text_color is not None else 0)
        self.text_color_combo.currentIndexChanged.connect(self._on_text_color_mode_changed)

        self.text_color_swatch_button = QPushButton(self)
        self.text_color_swatch_button.setFixedSize(*_SWATCH_SIZE)
        self.text_color_swatch_button.setIconSize(_SWATCH_ICON_SIZE)
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
        self.swatch_button.setIcon(swatch_icon(self._hex, orphaned=self.orphaned, size=20))
        text_hex = self._text_color or auto_text_color(self._hex)
        self.text_color_swatch_button.setIcon(swatch_icon(text_hex, size=20))
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

    def set_read_only(self, read_only: bool) -> None:
        self.swatch_button.setEnabled(not read_only)
        self.label_edit.setReadOnly(read_only)
        self.text_color_combo.setEnabled(not read_only)
        self.text_color_swatch_button.setEnabled(not read_only)
        self.remove_button.setEnabled(not read_only)

    def to_slot(self) -> Slot:
        return Slot(
            id=self.slot_id,
            label=self.label_edit.text().strip(),
            hex=self._hex,
            text_color=self._text_color,
            orphaned=self.orphaned,
        )


class ThemeEditorWidget(QWidget):
    """Edits a Theme's background color and its arbitrary-length slot
    list: add/remove/reorder (drag, via the list's own internal-move
    support) plus per-slot color/label/text-color. Doesn't change the
    theme's own id/name/origin — those are decided elsewhere (Duplicate,
    the theme picker).

    A plain QWidget rather than a QDialog: it's hosted inside the
    Settings dialog's Themes pane (embedded via set_theme(), swapped to
    view/edit whichever theme is selected in that pane's theme list),
    with no OK/Cancel of its own — the outer dialog owns commit/cancel
    for the whole Settings window."""

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme_id = theme.id
        self._theme_name = theme.name
        self._theme_origin = theme.origin
        self._background_color = theme.background_color
        # No editor UI for these yet -- carried through untouched so
        # editing a theme's slots/background never silently resets its
        # link styling back to the dataclass default.
        self._link_color = theme.link_color
        self._link_color_mode = theme.link_color_mode
        self._link_weight = theme.link_weight

        self.slot_list = QListWidget(self)
        self.slot_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        # QListWidget's own sizeHint() ignores its items' actual widths (it
        # falls back to a small generic default), which left this list --
        # and every ancestor sizing itself off of it -- too narrow to show
        # a row's text-color combo without horizontal scrolling.
        self.slot_list.setMinimumWidth(440)

        self.add_slot_button = QPushButton("Add Slot", self)
        self.add_slot_button.clicked.connect(self._on_add_slot)

        self.background_swatch_button = QPushButton(self)
        self.background_swatch_button.setFixedSize(*_SWATCH_SIZE)
        self.background_swatch_button.clicked.connect(self._pick_background_color)

        self._toolbar_row = QHBoxLayout()
        self._toolbar_row.addWidget(self.add_slot_button)
        self._toolbar_row.addStretch()
        self._toolbar_row.addWidget(QLabel("Background:", self))
        self._toolbar_row.addWidget(self.background_swatch_button)

        layout = QVBoxLayout(self)
        layout.addLayout(self._toolbar_row)
        layout.addWidget(self.slot_list)

        self._read_only = False
        for slot in theme.slots:
            self._add_row(slot)
        self._refresh_background_swatch()

    def _row_widget(self, index: int) -> ThemeSlotRowWidget:
        return self.slot_list.itemWidget(self.slot_list.item(index))

    def _add_row(self, slot: Slot) -> None:
        item = QListWidgetItem(self.slot_list)
        row_widget = ThemeSlotRowWidget(slot, self)
        row_widget.remove_button.clicked.connect(lambda: self._on_remove_row(item))
        row_widget.set_read_only(self._read_only)
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

    def set_theme_name(self, name: str) -> None:
        """Updates just the name result_theme() will report -- there's no
        name field in this widget's own UI (id/name/origin are decided
        elsewhere), but a caller renaming the theme this widget is
        currently showing (e.g. the Themes pane's list-row rename) needs
        result_theme() to reflect it, or the next set_theme()/
        result_theme() round-trip would silently revert the rename back
        to whatever name was showing when set_theme() was last called."""
        self._theme_name = name

    def set_theme(self, theme: Theme) -> None:
        """Repoints this widget at a different theme, discarding whatever
        unsaved edits were showing for the previous one — callers that
        need to keep those edits (the Themes pane's per-theme staging)
        must call result_theme() first and hold onto it themselves."""
        self._theme_id = theme.id
        self._theme_name = theme.name
        self._theme_origin = theme.origin
        self._background_color = theme.background_color
        self._link_color = theme.link_color
        self._link_color_mode = theme.link_color_mode
        self._link_weight = theme.link_weight
        self.slot_list.clear()
        for slot in theme.slots:
            self._add_row(slot)
        self._refresh_background_swatch()

    def set_read_only(self, read_only: bool) -> None:
        """Disables every editing control -- used for a preset theme that
        isn't the open document's own current theme, where there is no
        library entry to save an edit back to."""
        self._read_only = read_only
        self.add_slot_button.setEnabled(not read_only)
        self.background_swatch_button.setEnabled(not read_only)
        for i in range(self.slot_list.count()):
            self._row_widget(i).set_read_only(read_only)

    def result_theme(self) -> Theme:
        slots = [self._row_widget(i).to_slot() for i in range(self.slot_list.count())]
        return Theme(
            id=self._theme_id,
            name=self._theme_name,
            origin=self._theme_origin,
            background_color=self._background_color,
            link_color=self._link_color,
            link_color_mode=self._link_color_mode,
            link_weight=self._link_weight,
            slots=slots,
        )
