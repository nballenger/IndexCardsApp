from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from indexcards.models.theme import Theme, duplicate_theme
from indexcards.theme_library import ThemeLibrary
from indexcards.utils.ids import new_theme_id

_SWATCH_SIZE = 14


class ThemeRowWidget(QWidget):
    """One row: the theme's name (presets tagged distinctly, since
    they're read-only) plus a small strip of its slot colors — including
    any orphaned ones, since this is a whole-theme preview, not a
    per-card color picker."""

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.theme_id = theme.id

        label_text = f"{theme.name} (preset)" if theme.origin == "preset" else theme.name
        layout = QHBoxLayout(self)
        layout.addWidget(QLabel(label_text, self))
        layout.addStretch()
        for slot in theme.slots:
            swatch = QLabel(self)
            swatch.setFixedSize(_SWATCH_SIZE, _SWATCH_SIZE)
            swatch.setStyleSheet(f"background-color: {slot.hex}; border: 1px solid gray;")
            layout.addWidget(swatch)


class ThemePickerDialog(QDialog):
    """Lets the user pick a theme (preset or custom) to switch the
    document to, and duplicate any theme into a new custom one without
    leaving the dialog."""

    def __init__(
        self,
        available_themes: list[Theme],
        current_theme_id: str,
        theme_library: ThemeLibrary,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Switch Theme")
        self._theme_library = theme_library
        self._themes: list[Theme] = list(available_themes)

        self.theme_list = QListWidget(self)
        self._populate(current_theme_id)

        self.duplicate_button = QPushButton("Duplicate…", self)
        self.duplicate_button.clicked.connect(self._on_duplicate)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        button_row = QHBoxLayout()
        button_row.addWidget(self.duplicate_button)
        button_row.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(self.theme_list)
        layout.addLayout(button_row)
        layout.addWidget(button_box)

    def _populate(self, select_theme_id: str | None) -> None:
        self.theme_list.clear()
        for theme in self._themes:
            item = QListWidgetItem(self.theme_list)
            row_widget = ThemeRowWidget(theme, self)
            self.theme_list.addItem(item)
            self.theme_list.setItemWidget(item, row_widget)
            item.setSizeHint(row_widget.sizeHint())
            if select_theme_id is not None and theme.id == select_theme_id:
                self.theme_list.setCurrentItem(item)

    def _on_duplicate(self) -> None:
        item = self.theme_list.currentItem()
        if item is None:
            return
        source_id = self.theme_list.itemWidget(item).theme_id
        source = next(theme for theme in self._themes if theme.id == source_id)
        name, ok = QInputDialog.getText(
            self, "Duplicate Theme", "New theme name:", text=f"{source.name} Copy"
        )
        if not ok or not name.strip():
            return
        existing_ids = {theme.id for theme in self._themes}
        new_theme = duplicate_theme(source, new_theme_id(existing_ids), name.strip())
        self._theme_library.add(new_theme)
        self._themes.append(new_theme)
        self._populate(new_theme.id)

    def chosen_theme(self) -> Theme | None:
        item = self.theme_list.currentItem()
        if item is None:
            return None
        chosen_id = self.theme_list.itemWidget(item).theme_id
        return next((theme for theme in self._themes if theme.id == chosen_id), None)
