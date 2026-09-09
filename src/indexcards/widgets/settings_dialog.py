from __future__ import annotations

from dataclasses import replace
from enum import IntEnum

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from indexcards.app_settings import (
    DEFAULT_ARRANGE_COLUMN_LIMIT,
    DEFAULT_VIEW_ON_OPEN,
    GATHER_STACKS_EDGE_OPTIONS,
    MIN_ARRANGE_COLUMN_LIMIT,
    MINIMUM_FONT_SIZE_OPTIONS,
    VIEW_ON_OPEN_OPTIONS,
)
from indexcards.models.presets import PRESET_THEMES
from indexcards.models.theme import Theme, duplicate_theme
from indexcards.utils.ids import new_theme_id
from indexcards.utils.settings_icons import gear_icon, paintbrush_icon, warning_icon
from indexcards.widgets.theme_editor_widget import ThemeEditorWidget


class _GeneralPane(QWidget):
    """Auto-arrange column limiting, Gather Stacks target edge, and which
    canvas view an opened document starts at."""

    def __init__(
        self,
        limit_arrange_columns: bool,
        arrange_column_limit: int,
        gather_stacks_edge: str,
        view_on_open: str,
        minimum_font_size: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

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

        self.minimum_font_size_combo = QComboBox(self)
        for value, label in MINIMUM_FONT_SIZE_OPTIONS:
            self.minimum_font_size_combo.addItem(label, value)
        position = self.minimum_font_size_combo.findData(minimum_font_size)
        self.minimum_font_size_combo.setCurrentIndex(position if position >= 0 else 0)

        self.view_on_open_radios: dict[str, QRadioButton] = {}
        view_on_open_group = QButtonGroup(self)
        for value, label in VIEW_ON_OPEN_OPTIONS:
            radio = QRadioButton(label, self)
            radio.setChecked(value == view_on_open)
            view_on_open_group.addButton(radio)
            self.view_on_open_radios[value] = radio

        column_limit_row = QHBoxLayout()
        column_limit_row.addWidget(self.limit_arrange_columns_checkbox)
        column_limit_row.addWidget(self.arrange_column_limit_edit)
        column_limit_row.addStretch()

        gather_stacks_row = QHBoxLayout()
        gather_stacks_row.addWidget(QLabel("Gather Stacks to:", self))
        gather_stacks_row.addWidget(self.gather_stacks_edge_combo)
        gather_stacks_row.addStretch()

        minimum_font_size_row = QHBoxLayout()
        minimum_font_size_row.addWidget(QLabel("Minimum font size:", self))
        minimum_font_size_row.addWidget(self.minimum_font_size_combo)
        minimum_font_size_row.addStretch()

        layout = QVBoxLayout(self)
        layout.addLayout(column_limit_row)
        layout.addLayout(gather_stacks_row)
        layout.addLayout(minimum_font_size_row)
        layout.addWidget(QLabel("Document view on file open:", self))
        for value, _label in VIEW_ON_OPEN_OPTIONS:
            layout.addWidget(self.view_on_open_radios[value])
        layout.addStretch()

    def view_on_open(self) -> str:
        for value, radio in self.view_on_open_radios.items():
            if radio.isChecked():
                return value
        return DEFAULT_VIEW_ON_OPEN


class _WarningsPane(QWidget):
    """Confirmation prompts that can be silenced from Settings."""

    def __init__(self, warn_before_delete: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.warn_before_delete_checkbox = QCheckBox("Warn before deleting cards?", self)
        self.warn_before_delete_checkbox.setChecked(warn_before_delete)

        layout = QVBoxLayout(self)
        layout.addWidget(self.warn_before_delete_checkbox)
        layout.addStretch()


class _ThemeListRowWidget(QWidget):
    """One row in the Themes pane's left list: the theme's name (an
    always-present but normally read-only QLineEdit, so double-clicking a
    custom theme can rename it in place with no separate rename UI), and
    a small "Default" sub-label shown only while this theme is the
    pane's pending default."""

    renamed = Signal(str)

    def __init__(self, name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.name_edit = QLineEdit(name, self)
        self.name_edit.setFrame(False)
        self.name_edit.setReadOnly(True)
        self.name_edit.editingFinished.connect(self._on_editing_finished)

        self.default_label = QLabel("Default", self)
        self.default_label.setStyleSheet("color: gray; font-size: 10px;")
        self.default_label.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(0)
        layout.addWidget(self.name_edit)
        layout.addWidget(self.default_label)

    def _on_editing_finished(self) -> None:
        self.name_edit.setReadOnly(True)
        self.renamed.emit(self.name_edit.text().strip())

    def start_rename(self) -> None:
        self.name_edit.setReadOnly(False)
        self.name_edit.setFocus()
        self.name_edit.selectAll()

    def set_name(self, name: str) -> None:
        self.name_edit.setText(name)

    def set_is_default(self, is_default: bool) -> None:
        self.default_label.setVisible(is_default)


class _ThemesPane(QWidget):
    """Terminal.app-style theme picker: a left list of every available
    theme (presets, then the custom-theme library) with Default/+/-
    controls, and a right-hand ThemeEditorWidget editing whichever theme
    is selected.

    Everything here is staged locally -- color edits, renames, new/
    deleted themes, and the pending default -- and only reaches
    ThemeLibrary/AppSettings/Document when the outer SettingsDialog is
    Accepted, via pending_theme_library_upserts()/removals()/
    edited_document_theme()/document_theme_was_deleted(). This mirrors
    the rest of the dialog, where nothing commits until OK, and is what
    makes Cancel fully discard everything done in this pane."""

    def __init__(
        self,
        available_themes: list[Theme],
        default_theme_id: str,
        document_theme: Theme | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._document_theme_id = document_theme.id if document_theme is not None else None

        self._theme_order: list[str] = [theme.id for theme in available_themes]
        self._pending_themes: dict[str, Theme] = {theme.id: theme for theme in available_themes}
        if document_theme is not None:
            # The document's own live snapshot (which may differ from a
            # same-id library/preset entry, e.g. it has orphaned slots)
            # is what the pane should actually show and diff against --
            # not a generic stand-in from available_themes.
            self._pending_themes[document_theme.id] = document_theme
            if document_theme.id not in self._theme_order:
                self._theme_order.append(document_theme.id)
        self._original_themes: dict[str, Theme] = dict(self._pending_themes)
        self._items: dict[str, QListWidgetItem] = {}
        self._current_theme_id: str | None = None
        self._pending_deleted_theme_ids: set[str] = set()
        self._newly_created_theme_ids: set[str] = set()

        if default_theme_id in self._pending_themes:
            self._pending_default_theme_id = default_theme_id
        else:
            self._pending_default_theme_id = self._theme_order[0]

        self.theme_list = QListWidget(self)
        self.theme_list.currentItemChanged.connect(self._on_selection_changed)
        self.theme_list.itemDoubleClicked.connect(self._on_item_double_clicked)

        self.default_button = QPushButton("Default", self)
        self.default_button.clicked.connect(self._on_default_clicked)
        self.add_button = QPushButton("+", self)
        self.add_button.clicked.connect(self._on_add_clicked)
        self.remove_button = QPushButton("−", self)
        self.remove_button.clicked.connect(self._on_remove_clicked)

        buttons_row = QHBoxLayout()
        buttons_row.addWidget(self.default_button)
        buttons_row.addStretch()
        buttons_row.addWidget(self.add_button)
        buttons_row.addWidget(self.remove_button)

        left_layout = QVBoxLayout()
        left_layout.addWidget(self.theme_list)
        left_layout.addLayout(buttons_row)
        left_widget = QWidget(self)
        left_widget.setLayout(left_layout)

        self.editor = ThemeEditorWidget(self._pending_themes[self._theme_order[0]], self)

        layout = QHBoxLayout(self)
        layout.addWidget(left_widget)
        layout.addWidget(self.editor, 1)

        for theme_id in self._theme_order:
            self._add_list_row(theme_id)

        select_id = self._document_theme_id or self._pending_default_theme_id
        self._select_row(select_id)

    def _is_editable(self, theme_id: str) -> bool:
        theme = self._pending_themes.get(theme_id)
        if theme is None:
            return False
        return theme.origin == "custom" or theme_id == self._document_theme_id

    def _is_removable(self, theme_id: str) -> bool:
        theme = self._pending_themes.get(theme_id)
        return theme is not None and theme.origin == "custom"

    def _add_list_row(self, theme_id: str) -> None:
        theme = self._pending_themes[theme_id]
        item = QListWidgetItem(self.theme_list)
        item.setData(Qt.ItemDataRole.UserRole, theme_id)
        row_widget = _ThemeListRowWidget(theme.name, self)
        row_widget.renamed.connect(lambda name, tid=theme_id: self._on_row_renamed(tid, name))
        row_widget.set_is_default(theme_id == self._pending_default_theme_id)
        self.theme_list.addItem(item)
        self.theme_list.setItemWidget(item, row_widget)
        item.setSizeHint(row_widget.sizeHint())
        self._items[theme_id] = item

    def _remove_list_row(self, theme_id: str) -> None:
        item = self._items.pop(theme_id, None)
        if item is not None:
            self.theme_list.takeItem(self.theme_list.row(item))

    def _select_row(self, theme_id: str) -> None:
        item = self._items.get(theme_id)
        if item is not None:
            self.theme_list.setCurrentItem(item)

    def _row_widget_for(self, theme_id: str) -> _ThemeListRowWidget | None:
        item = self._items.get(theme_id)
        return self.theme_list.itemWidget(item) if item is not None else None

    def _refresh_default_labels(self) -> None:
        for theme_id, item in self._items.items():
            self.theme_list.itemWidget(item).set_is_default(
                theme_id == self._pending_default_theme_id
            )

    def _on_selection_changed(
        self, current: QListWidgetItem | None, previous: QListWidgetItem | None
    ) -> None:
        if previous is not None:
            prev_id = previous.data(Qt.ItemDataRole.UserRole)
            if prev_id in self._pending_themes:
                self._pending_themes[prev_id] = self.editor.result_theme()
        if current is None:
            self._current_theme_id = None
            return
        theme_id = current.data(Qt.ItemDataRole.UserRole)
        self._current_theme_id = theme_id
        self.editor.set_theme(self._pending_themes[theme_id])
        self.editor.set_read_only(not self._is_editable(theme_id))
        self.remove_button.setEnabled(self._is_removable(theme_id))

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        theme_id = item.data(Qt.ItemDataRole.UserRole)
        if self._pending_themes[theme_id].origin != "custom":
            return
        widget = self.theme_list.itemWidget(item)
        if widget is not None:
            widget.start_rename()

    def _on_row_renamed(self, theme_id: str, name: str) -> None:
        theme = self._pending_themes.get(theme_id)
        if theme is None or not name:
            row = self._row_widget_for(theme_id)
            if row is not None and theme is not None:
                row.set_name(theme.name)
            return
        # A fresh object, not an in-place mutation: _original_themes and
        # _pending_themes share object identity for anything not yet
        # replaced by the editor's own result_theme(), so mutating
        # theme.name here would silently corrupt the "original" baseline
        # too and make this rename invisible to the diff in
        # pending_theme_library_upserts().
        self._pending_themes[theme_id] = replace(theme, name=name)
        if theme_id == self._current_theme_id:
            # The editor's own result_theme() would otherwise echo back
            # whatever name was current when set_theme() last ran,
            # silently reverting this rename the next time its state is
            # captured (e.g. on the next selection change or Accept).
            self.editor.set_theme_name(name)
        row = self._row_widget_for(theme_id)
        if row is not None:
            row.set_name(name)

    def _on_default_clicked(self) -> None:
        if self._current_theme_id is None:
            return
        self._pending_default_theme_id = self._current_theme_id
        self._refresh_default_labels()

    def _on_add_clicked(self) -> None:
        if self._current_theme_id is None:
            return
        source = self._pending_themes[self._current_theme_id]
        new_id = new_theme_id(self._pending_themes.keys())
        new_theme = duplicate_theme(source, new_id, f"{source.name} Copy")
        self._pending_themes[new_id] = new_theme
        self._newly_created_theme_ids.add(new_id)
        self._theme_order.append(new_id)
        self._add_list_row(new_id)
        self._select_row(new_id)
        row = self._row_widget_for(new_id)
        if row is not None:
            row.start_rename()

    def _on_remove_clicked(self) -> None:
        theme_id = self._current_theme_id
        if theme_id is None or not self._is_removable(theme_id):
            return
        self._pending_themes.pop(theme_id, None)
        if theme_id not in self._newly_created_theme_ids:
            self._pending_deleted_theme_ids.add(theme_id)
        self._newly_created_theme_ids.discard(theme_id)
        self._theme_order.remove(theme_id)
        if self._pending_default_theme_id == theme_id:
            self._pending_default_theme_id = PRESET_THEMES[0].id
        self._remove_list_row(theme_id)
        self._refresh_default_labels()
        fallback_id = (
            self._pending_default_theme_id
            if self._pending_default_theme_id in self._pending_themes
            else self._theme_order[0]
        )
        self._select_row(fallback_id)

    def pending_default_theme_id(self) -> str:
        return self._pending_default_theme_id

    def _commit_current_selection(self) -> None:
        """Captures whatever the editor currently shows into
        _pending_themes for the selected theme. Selection changes already
        do this in _on_selection_changed, but nothing else updates the
        pending copy for the theme that's *still* selected when the
        outer dialog is accepted -- called defensively from every getter
        that reads _pending_themes, so it doesn't matter whether the real
        Qt event loop or a test's replaced exec() is what leads here."""
        if self._current_theme_id is not None and self._current_theme_id in self._pending_themes:
            self._pending_themes[self._current_theme_id] = self.editor.result_theme()

    def pending_theme_library_upserts(self) -> list[Theme]:
        self._commit_current_selection()
        upserts = []
        for theme_id, theme in self._pending_themes.items():
            if theme.origin != "custom" or theme_id == self._document_theme_id:
                continue
            if theme_id in self._newly_created_theme_ids or theme != self._original_themes.get(
                theme_id
            ):
                upserts.append(theme)
        return upserts

    def pending_theme_library_removals(self) -> list[str]:
        return [
            theme_id
            for theme_id in self._pending_deleted_theme_ids
            if theme_id not in self._newly_created_theme_ids
        ]

    def edited_document_theme(self) -> Theme | None:
        if self._document_theme_id is None:
            return None
        self._commit_current_selection()
        theme = self._pending_themes.get(self._document_theme_id)
        if theme is None or theme == self._original_themes.get(self._document_theme_id):
            return None
        return theme

    def document_theme_was_deleted(self) -> bool:
        return (
            self._document_theme_id is not None
            and self._document_theme_id in self.pending_theme_library_removals()
        )


class SettingsDialog(QDialog):
    """Application-level preferences, organized into a Terminal.app-style
    multi-pane layout: General (auto-arrange column limiting, Gather
    Stacks target edge, view-on-open), Themes (pick/edit/create/delete
    themes and set the default), and Warnings (delete-confirmation
    prompts)."""

    class Pane(IntEnum):
        GENERAL = 0
        THEMES = 1
        WARNINGS = 2

    def __init__(
        self,
        warn_before_delete: bool,
        default_theme_id: str,
        available_themes: list[Theme],
        limit_arrange_columns: bool,
        arrange_column_limit: int,
        gather_stacks_edge: str,
        view_on_open: str,
        minimum_font_size: int,
        document_theme: Theme | None = None,
        initial_pane: Pane = Pane.GENERAL,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")

        self._general_pane = _GeneralPane(
            limit_arrange_columns,
            arrange_column_limit,
            gather_stacks_edge,
            view_on_open,
            minimum_font_size,
            self,
        )
        self._warnings_pane = _WarningsPane(warn_before_delete, self)
        self._themes_pane = _ThemesPane(available_themes, default_theme_id, document_theme, self)

        # Flat pass-through attributes so most callers/tests can keep
        # addressing these controls directly on the dialog, unaware they
        # now live inside a pane sub-widget.
        self.warn_before_delete_checkbox = self._warnings_pane.warn_before_delete_checkbox
        self.limit_arrange_columns_checkbox = self._general_pane.limit_arrange_columns_checkbox
        self.arrange_column_limit_edit = self._general_pane.arrange_column_limit_edit
        self.gather_stacks_edge_combo = self._general_pane.gather_stacks_edge_combo
        self.minimum_font_size_combo = self._general_pane.minimum_font_size_combo
        self._view_on_open_radios = self._general_pane.view_on_open_radios
        self.themes_pane = self._themes_pane

        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._general_pane)
        self._stack.addWidget(self._themes_pane)
        self._stack.addWidget(self._warnings_pane)

        self._nav_buttons: dict[SettingsDialog.Pane, QToolButton] = {}
        nav_group = QButtonGroup(self)
        nav_group.setExclusive(True)
        nav_row = QHBoxLayout()
        nav_row.addStretch()
        for pane, label, icon in (
            (SettingsDialog.Pane.GENERAL, "General", gear_icon()),
            (SettingsDialog.Pane.THEMES, "Themes", paintbrush_icon()),
            (SettingsDialog.Pane.WARNINGS, "Warnings", warning_icon()),
        ):
            button = QToolButton(self)
            button.setText(label)
            button.setIcon(icon)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setCheckable(True)
            button.setAutoRaise(True)
            button.clicked.connect(lambda _checked=False, p=pane: self.show_pane(p))
            nav_group.addButton(button)
            self._nav_buttons[pane] = button
            nav_row.addWidget(button)
        nav_row.addStretch()

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(nav_row)
        layout.addWidget(self._stack)
        layout.addWidget(button_box)

        # Fixed size across every pane (rather than Terminal.app's own
        # per-pane resize) -- simpler, and avoids the window visibly
        # jumping when switching to/from the widest pane (Themes).
        self._stack.setMinimumSize(self._themes_pane.sizeHint())

        self.show_pane(initial_pane)

    def show_pane(self, pane: Pane) -> None:
        self._stack.setCurrentIndex(int(pane))
        self._nav_buttons[pane].setChecked(True)

    def warn_before_delete(self) -> bool:
        return self.warn_before_delete_checkbox.isChecked()

    def default_theme_id(self) -> str:
        return self._themes_pane.pending_default_theme_id()

    def pending_theme_library_upserts(self) -> list[Theme]:
        return self._themes_pane.pending_theme_library_upserts()

    def pending_theme_library_removals(self) -> list[str]:
        return self._themes_pane.pending_theme_library_removals()

    def edited_document_theme(self) -> Theme | None:
        return self._themes_pane.edited_document_theme()

    def document_theme_was_deleted(self) -> bool:
        return self._themes_pane.document_theme_was_deleted()

    def limit_arrange_columns(self) -> bool:
        return self.limit_arrange_columns_checkbox.isChecked()

    def arrange_column_limit(self) -> int:
        return int(self.arrange_column_limit_edit.text())

    def gather_stacks_edge(self) -> str:
        return self.gather_stacks_edge_combo.currentData()

    def minimum_font_size(self) -> int:
        return self.minimum_font_size_combo.currentData()

    def view_on_open(self) -> str:
        return self._general_pane.view_on_open()

    def accept(self) -> None:
        if self.limit_arrange_columns_checkbox.isChecked():
            text = self.arrange_column_limit_edit.text().strip()
            if not text.isdigit() or int(text) < MIN_ARRANGE_COLUMN_LIMIT:
                self.arrange_column_limit_edit.setText(str(DEFAULT_ARRANGE_COLUMN_LIMIT))
        super().accept()
