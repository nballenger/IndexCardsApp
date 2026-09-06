from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QByteArray, QEvent, QMimeData, QModelIndex, Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QClipboard,
    QCloseEvent,
    QColor,
    QKeySequence,
    QShortcut,
    QTextDocument,
    QUndoGroup,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QDialog,
    QFileDialog,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QToolBar,
)

from indexcards.app_settings import AppSettings
from indexcards.arrange.auto_arrange import (
    ARRANGE_AVOIDANCE_GUTTER,
    arrange_avoiding_obstacles,
    arrange_by_tile,
    arrange_cards_sweep_to_edges,
    arrange_cards_tidy_to_edges,
    arrange_stacks_to_edge,
    avoid_card_overlap,
    compute_center_rect,
    positions_bbox,
    shift_layout_to_clear,
    union_bbox,
)
from indexcards.arrange.link_arrange import arrange_by_untangle_links, arrange_untangle_touching
from indexcards.canvas.canvas_scene import CanvasScene
from indexcards.canvas.canvas_view import VIEW_EXTENTS_MARGIN, CanvasView
from indexcards.canvas.card_item import CardItem
from indexcards.commands.arrange_commands import AutoArrangeCommand
from indexcards.commands.card_commands import (
    ChangeColorsCommand,
    DeleteCardCommand,
    TogglePinCommand,
)
from indexcards.commands.document_commands import (
    ChangeCanvasBackgroundCommand,
    ChangeDefaultLineEndingCommand,
    ChangeLinkColorModeCommand,
    ChangeLinkWeightCommand,
)
from indexcards.commands.link_commands import (
    AddLinkCommand,
    ChangeLinkLineEndingsCommand,
    DeleteLinkCommand,
)
from indexcards.commands.stack_commands import (
    GatherStacksCommand,
    RemoveStackCommand,
    push_delete_stack_and_cards,
    push_paste,
)
from indexcards.commands.theme_commands import (
    KeepOrphanColorCommand,
    ReassignOrphanColorCommand,
    SetDocumentThemeCommand,
)
from indexcards.list_view.card_table_model import CardTableModel
from indexcards.list_view.list_view_widget import ListViewWidget
from indexcards.models.card import Card
from indexcards.models.document import Document
from indexcards.models.link import LINE_ENDING_OPTIONS, Link
from indexcards.models.presets import PRESET_THEMES
from indexcards.models.stack import Stack
from indexcards.models.theme import Theme, duplicate_theme
from indexcards.models.theme_resolution import resolve_default_theme
from indexcards.persistence.file_io import load_document, save_document
from indexcards.theme_library import ThemeLibrary
from indexcards.utils.clipboard_format import (
    CLIPBOARD_MIME_TYPE,
    build_clipboard_payload,
    card_texts_from_plain_text,
    cards_and_stacks_from_payload,
    plain_text_for_payload,
)
from indexcards.utils.color_icons import swatch_icon
from indexcards.utils.ids import new_card_id, new_link_id, new_theme_id
from indexcards.utils.line_ending_icons import line_ending_icon
from indexcards.utils.line_weight_icons import line_weight_icon
from indexcards.widgets.dialogs import confirm_delete_cards
from indexcards.widgets.orphan_resolution_dialog import OrphanResolutionDialog
from indexcards.widgets.search_bar import SearchBar
from indexcards.widgets.settings_dialog import SettingsDialog
from indexcards.widgets.stack_dialogs import confirm_delete_stack
from indexcards.widgets.theme_editor_dialog import ThemeEditorDialog

if TYPE_CHECKING:
    from indexcards.window_manager import WindowManager

FILE_DIALOG_FILTER = "Index Cards Files (*.idxcards);;All Files (*)"


def _card_text_to_logical(markdown_text: str) -> str:
    """Card.text is stored as markdown (see card_item.py's _commit_text)
    — a hard line break between two blocks becomes a blank-line block
    separator (Qt's toMarkdown() convention: "Alpha\\n\\nBravo" for two
    lines "Alpha"/"Bravo"), not a single \\n. Escaping that raw text
    verbatim for clipboard export would turn one hard break into a
    literal doubled \\n\\n. This converts to "logical" text — exactly
    one \\n per hard line break, matching normal plain-text expectations
    — by round-tripping through the same QTextDocument markdown parser
    the card editor itself uses; it also incidentally strips markdown
    formatting syntax (bold/italic markers), so exported text shows
    clean words rather than raw markdown."""
    document = QTextDocument()
    document.setMarkdown(markdown_text)
    return document.toPlainText()


def _logical_text_to_card_text(logical_text: str) -> str:
    """The inverse, for building a new Card.text from external plain
    text: expands a single \\n into markdown's own double-newline block
    separator, so the result renders as real separate lines the next
    time it's loaded via setMarkdown() — a single bare \\n there is just
    a soft break within one paragraph (rendered space-joined), not a new
    block, so without this a pasted-in multi-line card would silently
    collapse onto one line the moment it's next opened for editing."""
    return logical_text.replace("\n", "\n\n")


class MainWindow(QMainWindow):
    """One window per open file."""

    def __init__(self, window_manager: WindowManager | None = None) -> None:
        super().__init__()
        self._window_manager = window_manager
        self._undo_group = (
            window_manager.undo_group if window_manager is not None else QUndoGroup(self)
        )
        self._settings = window_manager.settings if window_manager is not None else AppSettings()
        self._theme_library = (
            window_manager.theme_library if window_manager is not None else ThemeLibrary()
        )

        self.document: Document | None = None
        self.card_table_model: CardTableModel | None = None
        self.canvas_scene: CanvasScene | None = None
        self.undo_stack: QUndoStack | None = None
        self._current_path: Path | None = None
        self._syncing_selection = False
        self._current_search_query = ""
        self._links_visible = True
        self._links_emphasized = False

        self.setWindowTitle("Index Cards")
        self.resize(1000, 700)

        self.canvas_view = CanvasView(self)
        self.list_view = ListViewWidget(self, settings=self._settings)
        self.view_stack = QStackedWidget(self)
        self.view_stack.addWidget(self.canvas_view)
        self.view_stack.addWidget(self.list_view)
        self.setCentralWidget(self.view_stack)

        # Permanent (right-aligned, not the scrolling-message area) status
        # readout -- currently just Links on/off, but the intent is to grow
        # this into context-sensitive info (e.g. what a hovered object
        # supports) later, so it's its own widget/update method rather than
        # an inline statusBar().showMessage() call.
        self.links_status_label = QLabel(self)
        self.statusBar().addPermanentWidget(self.links_status_label)
        self._update_links_status_label()

        self.list_view.currentCardChanged.connect(self._on_list_current_card_changed)
        self.list_view.cardCreated.connect(self._select_and_focus_new_card)
        self.canvas_view.link_controller.linkRequested.connect(self._on_link_requested)
        self.canvas_view.deleteRequested.connect(self._on_canvas_delete_requested)
        self.canvas_view.cardCreated.connect(self._select_and_focus_new_card)
        self.canvas_view.backgroundChangeRequested.connect(self._on_change_canvas_background)

        # Link Mode is entered by holding Option (Qt's AltModifier — the
        # physical key Qt calls "Alt" is labelled "Option" on Mac
        # keyboards) rather than a toggle button, so it has to be tracked
        # at the application level: a plain keyPressEvent override on
        # canvas_view would miss the key whenever some other widget (the
        # search bar, a card being text-edited) has focus instead.
        QApplication.instance().installEventFilter(self)

        self.search_bar = SearchBar(self)
        self.search_bar.queryChanged.connect(self._on_search_query_changed)
        self.search_toolbar = QToolBar("Search", self)
        self.search_toolbar.addWidget(self.search_bar)
        self.addToolBar(self.search_toolbar)

        find_shortcut = QShortcut(QKeySequence.StandardKey.Find, self)
        find_shortcut.activated.connect(self._focus_search_bar)

        self._build_menu()
        self._set_document(
            Document(
                name="Untitled",
                theme=resolve_default_theme(self._settings, self._theme_library),
            ),
            path=None,
        )

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")

        self.settings_action = QAction("Settings...", self)
        self.settings_action.setShortcut(QKeySequence.StandardKey.Preferences)
        self.settings_action.setMenuRole(QAction.MenuRole.PreferencesRole)
        self.settings_action.triggered.connect(self._on_open_settings)
        file_menu.addAction(self.settings_action)
        file_menu.addSeparator()

        new_action = QAction("&New Window", self)
        new_action.setShortcut(QKeySequence.StandardKey.New)
        new_action.triggered.connect(self._on_new)
        file_menu.addAction(new_action)

        new_card_action = QAction("New &Card", self)
        new_card_action.setShortcut(QKeySequence("Ctrl+Shift+N"))
        new_card_action.triggered.connect(self._on_create_card_shortcut)
        file_menu.addAction(new_card_action)

        open_action = QAction("&Open...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self._on_open)
        file_menu.addAction(open_action)

        save_action = QAction("&Save", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self._on_save)
        file_menu.addAction(save_action)

        save_as_action = QAction("Save &As...", self)
        save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as_action.triggered.connect(self._on_save_as)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        close_action = QAction("Close Window", self)
        close_action.setShortcut(QKeySequence.StandardKey.Close)
        close_action.triggered.connect(self.close)
        file_menu.addAction(close_action)

        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        edit_menu = self.menuBar().addMenu("&Edit")

        undo_action = self._undo_group.createUndoAction(self, "&Undo")
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        edit_menu.addAction(undo_action)

        redo_action = self._undo_group.createRedoAction(self, "&Redo")
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        edit_menu.addAction(redo_action)

        edit_menu.addSeparator()

        self.cut_action = QAction("Cu&t", self)
        self.cut_action.setShortcut(QKeySequence.StandardKey.Cut)
        self.cut_action.triggered.connect(self._on_cut)
        edit_menu.addAction(self.cut_action)

        self.copy_action = QAction("&Copy", self)
        self.copy_action.setShortcut(QKeySequence.StandardKey.Copy)
        self.copy_action.triggered.connect(self._on_copy)
        edit_menu.addAction(self.copy_action)

        self.paste_action = QAction("&Paste", self)
        self.paste_action.setShortcut(QKeySequence.StandardKey.Paste)
        self.paste_action.triggered.connect(self._on_paste)
        edit_menu.addAction(self.paste_action)
        edit_menu.aboutToShow.connect(self._update_clipboard_actions_enabled)
        # A QAction's shortcut only fires while the action is actually
        # enabled — aboutToShow alone only refreshes that when the user
        # opens the Edit menu, so Cmd+X/C/V would silently do nothing after
        # a selection/clipboard change until the menu happened to be
        # opened. These keep the enabled state live so the shortcuts always
        # reflect current reality, matching how QApplication.clipboard()'s
        # own dataChanged signal fires — used directly here (not via
        # self._clipboard()) since this is a one-time construction-time
        # wiring to the real clipboard object, not a per-call access point.
        self.list_view.selectionChanged.connect(self._update_clipboard_actions_enabled)
        QApplication.clipboard().dataChanged.connect(self._update_clipboard_actions_enabled)
        self._update_clipboard_actions_enabled()

        edit_menu.addSeparator()

        select_all_action = QAction("Select &All", self)
        select_all_action.setShortcut(QKeySequence.StandardKey.SelectAll)
        select_all_action.triggered.connect(self._on_select_all)
        edit_menu.addAction(select_all_action)

        self.select_linked_action = QAction("Select &Linked", self)
        self.select_linked_action.triggered.connect(self._on_select_linked)
        edit_menu.addAction(self.select_linked_action)
        edit_menu.aboutToShow.connect(self._update_select_linked_enabled)
        self._update_select_linked_enabled()

        edit_menu.addSeparator()

        self.add_to_stack_menu = edit_menu.addMenu("Add to Stack")
        self._add_to_stack_dynamic_actions: list[QAction] = []
        edit_menu.aboutToShow.connect(self._rebuild_add_to_stack_menu)
        self._rebuild_add_to_stack_menu()

        self.remove_from_stack_action = QAction("Remove from Stack", self)
        self.remove_from_stack_action.triggered.connect(self._on_remove_from_stack)
        edit_menu.addAction(self.remove_from_stack_action)
        edit_menu.aboutToShow.connect(self._update_remove_from_stack_action)
        self._update_remove_from_stack_action()

        edit_menu.addSeparator()

        self.pin_action = QAction(self)
        self.pin_action.setShortcut(QKeySequence("Ctrl+Shift+P"))
        self.pin_action.triggered.connect(self._on_toggle_pin)
        edit_menu.addAction(self.pin_action)
        edit_menu.aboutToShow.connect(self._update_pin_action)
        self._update_pin_action()

        self.card_color_menu = edit_menu.addMenu("Card Color")
        self._card_color_dynamic_actions: list[QAction] = []
        edit_menu.aboutToShow.connect(self._rebuild_card_color_menu)
        self._rebuild_card_color_menu()

        self.delete_stack_action = QAction(self)
        self.delete_stack_action.triggered.connect(self._on_delete_stack)
        edit_menu.addAction(self.delete_stack_action)
        edit_menu.aboutToShow.connect(self._update_delete_stack_action)
        self._update_delete_stack_action()

        view_menu = self.menuBar().addMenu("&View")

        self.view_canvas_action = QAction("Canvas", self)
        self.view_canvas_action.setCheckable(True)
        self.view_canvas_action.setShortcut(QKeySequence("Ctrl+1"))
        self.view_canvas_action.triggered.connect(
            lambda: self.view_stack.setCurrentWidget(self.canvas_view)
        )
        view_menu.addAction(self.view_canvas_action)

        self.view_list_action = QAction("List", self)
        self.view_list_action.setCheckable(True)
        self.view_list_action.setShortcut(QKeySequence("Ctrl+2"))
        self.view_list_action.triggered.connect(
            lambda: self.view_stack.setCurrentWidget(self.list_view)
        )
        view_menu.addAction(self.view_list_action)

        view_action_group = QActionGroup(self)
        view_action_group.setExclusive(True)
        view_action_group.addAction(self.view_canvas_action)
        view_action_group.addAction(self.view_list_action)

        view_menu.addSeparator()

        self.view_extents_action = QAction("Extents", self)
        self.view_extents_action.setShortcut(QKeySequence("Ctrl+0"))
        self.view_extents_action.triggered.connect(self._on_view_extents)
        view_menu.addAction(self.view_extents_action)
        # Ctrl+0 has a real shortcut, so (per the project's own established
        # lesson — see the Cut/Copy/Paste enablement above) its enabled
        # state has to be kept live via a real signal, not just refreshed
        # on aboutToShow: openedChanged fires exactly when the answer to
        # "is the stack overlay open" actually changes.
        self.canvas_view.stack_overlay.openedChanged.connect(
            self._update_view_extents_action_enabled
        )
        self._update_view_extents_action_enabled()

        view_menu.addSeparator()

        self.toggle_links_action = QAction(self)
        self.toggle_links_action.setShortcut(QKeySequence("Ctrl+Shift+L"))
        self.toggle_links_action.triggered.connect(self._on_toggle_links_visible)
        view_menu.addAction(self.toggle_links_action)
        self._update_toggle_links_action_text()

        self.emphasize_links_action = QAction("Emphasize Links", self)
        self.emphasize_links_action.setCheckable(True)
        self.emphasize_links_action.setShortcut(QKeySequence("Ctrl+Shift+K"))
        self.emphasize_links_action.toggled.connect(self._on_toggle_emphasize_links)
        view_menu.addAction(self.emphasize_links_action)

        view_menu.addSeparator()

        self.toggle_color_key_action = QAction("Show Color Key", self)
        self.toggle_color_key_action.setCheckable(True)
        self.toggle_color_key_action.toggled.connect(self._on_toggle_color_key)
        view_menu.addAction(self.toggle_color_key_action)

        view_menu.addSeparator()

        self.canvas_background_action = QAction("Canvas Background", self)
        self.canvas_background_action.triggered.connect(self._on_change_canvas_background)
        view_menu.addAction(self.canvas_background_action)

        theme_menu = self.menuBar().addMenu("&Theme")
        self._theme_menu = theme_menu
        self._theme_list_actions: list[QAction] = []
        self._theme_list_group = QActionGroup(self)
        self._theme_list_group.setExclusive(True)

        self._theme_list_separator = theme_menu.addSeparator()

        self.edit_current_theme_action = QAction("Edit Current Theme…", self)
        self.edit_current_theme_action.triggered.connect(self._on_edit_current_theme)
        theme_menu.addAction(self.edit_current_theme_action)

        self.duplicate_theme_action = QAction("Duplicate Current Theme…", self)
        self.duplicate_theme_action.triggered.connect(self._on_duplicate_current_theme)
        theme_menu.addAction(self.duplicate_theme_action)

        theme_menu.addSeparator()

        self.resolve_orphaned_colors_action = QAction("Resolve Orphaned Colors…", self)
        self.resolve_orphaned_colors_action.triggered.connect(self._on_resolve_orphaned_colors)
        theme_menu.addAction(self.resolve_orphaned_colors_action)
        theme_menu.aboutToShow.connect(self._update_resolve_orphaned_colors_enabled)
        theme_menu.aboutToShow.connect(self._rebuild_theme_list_section)
        self._update_resolve_orphaned_colors_enabled()
        self._rebuild_theme_list_section()

        arrange_menu = self.menuBar().addMenu("&Arrange")

        self.arrange_tile_action = QAction("Tile", self)
        self.arrange_tile_action.triggered.connect(lambda: self._run_auto_arrange("tile"))
        arrange_menu.addAction(self.arrange_tile_action)

        self.arrange_scatter_action = QAction("Scatter", self)
        self.arrange_scatter_action.triggered.connect(lambda: self._run_auto_arrange("scatter"))
        arrange_menu.addAction(self.arrange_scatter_action)

        self.arrange_columns_menu = arrange_menu.addMenu("Columns")

        self.arrange_columns_by_color_action = QAction("By Color", self)
        self.arrange_columns_by_color_action.triggered.connect(
            lambda: self._run_auto_arrange("columns_color")
        )
        self.arrange_columns_menu.addAction(self.arrange_columns_by_color_action)

        self.arrange_columns_alphabetical_action = QAction("Alphabetical", self)
        self.arrange_columns_alphabetical_action.triggered.connect(
            lambda: self._run_auto_arrange("columns_alphabetical")
        )
        self.arrange_columns_menu.addAction(self.arrange_columns_alphabetical_action)

        arrange_menu.addSeparator()

        self.untangle_links_action = QAction("Untangle Links", self)
        self.untangle_links_action.triggered.connect(self._run_untangle_links)
        arrange_menu.addAction(self.untangle_links_action)

        arrange_menu.addSeparator()

        self.gather_stacks_action = QAction("Gather Stacks", self)
        self.gather_stacks_action.triggered.connect(self._on_gather_stacks)
        arrange_menu.addAction(self.gather_stacks_action)

        arrange_menu.addSeparator()

        self.tidy_to_edges_action = QAction("Tidy to Edges", self)
        self.tidy_to_edges_action.triggered.connect(lambda: self._run_edges_arrange("tidy"))
        arrange_menu.addAction(self.tidy_to_edges_action)

        self.sweep_to_edges_action = QAction("Sweep to Edges", self)
        self.sweep_to_edges_action.triggered.connect(lambda: self._run_edges_arrange("sweep"))
        arrange_menu.addAction(self.sweep_to_edges_action)

        arrange_menu.aboutToShow.connect(self._update_arrange_actions_enabled)
        self._update_arrange_actions_enabled()

        links_menu = self.menuBar().addMenu("&Links")

        self.link_line_endings_menu = links_menu.addMenu("Line Endings")
        self._line_ending_actions: dict[str, QAction] = {}
        line_ending_group = QActionGroup(self)
        line_ending_group.setExclusive(True)
        for value, label in LINE_ENDING_OPTIONS:
            icon = line_ending_icon(value)
            if icon is not None:
                action = self.link_line_endings_menu.addAction(icon, label)
            else:
                action = self.link_line_endings_menu.addAction(label)
            action.setCheckable(True)
            action.triggered.connect(
                lambda checked=False, v=value: self._on_change_line_endings(v)
            )
            line_ending_group.addAction(action)
            self._line_ending_actions[value] = action
        links_menu.aboutToShow.connect(self._update_line_endings_menu)
        self._update_line_endings_menu()

        styling_menu = links_menu.addMenu("Styling")

        line_weight_menu = styling_menu.addMenu("Line Weight")
        self._line_weight_actions: dict[int, QAction] = {}
        line_weight_group = QActionGroup(self)
        line_weight_group.setExclusive(True)
        for weight in range(1, 6):
            action = line_weight_menu.addAction(line_weight_icon(weight), f"{weight} px")
            action.setCheckable(True)
            action.triggered.connect(
                lambda checked=False, w=weight: self._on_change_link_weight(w)
            )
            line_weight_group.addAction(action)
            self._line_weight_actions[weight] = action
        line_weight_menu.aboutToShow.connect(self._update_line_weight_menu)
        self._update_line_weight_menu()

        line_color_menu = styling_menu.addMenu("Line Color")
        self._line_color_actions: dict[str, QAction] = {}
        line_color_group = QActionGroup(self)
        line_color_group.setExclusive(True)
        for mode, label, placeholder_hex in [
            ("theme", "Theme Color", "#808080"),
            ("white", "White", "#ffffff"),
            ("black", "Black", "#000000"),
        ]:
            action = line_color_menu.addAction(swatch_icon(placeholder_hex), label)
            action.setCheckable(True)
            action.triggered.connect(
                lambda checked=False, m=mode: self._on_change_link_color_mode(m)
            )
            line_color_group.addAction(action)
            self._line_color_actions[mode] = action
        line_color_menu.aboutToShow.connect(self._update_line_color_menu)
        self._update_line_color_menu()

        default_line_ending_menu = styling_menu.addMenu("Default Line Endings")
        self._default_line_ending_actions: dict[str, QAction] = {}
        default_line_ending_group = QActionGroup(self)
        default_line_ending_group.setExclusive(True)
        for value, label in LINE_ENDING_OPTIONS:
            icon = line_ending_icon(value)
            if icon is not None:
                action = default_line_ending_menu.addAction(icon, label)
            else:
                action = default_line_ending_menu.addAction(label)
            action.setCheckable(True)
            action.triggered.connect(
                lambda checked=False, v=value: self._on_change_default_line_ending(v)
            )
            default_line_ending_group.addAction(action)
            self._default_line_ending_actions[value] = action
        default_line_ending_menu.aboutToShow.connect(self._update_default_line_ending_menu)
        self._update_default_line_ending_menu()

        self.view_stack.currentChanged.connect(self._on_current_view_changed)
        self._on_current_view_changed(self.view_stack.currentIndex())

    def _on_current_view_changed(self, index: int) -> None:
        self._update_clipboard_actions_enabled()
        if self.view_stack.widget(index) is self.canvas_view:
            self.view_canvas_action.setChecked(True)
        elif self.view_stack.widget(index) is self.list_view:
            self.view_list_action.setChecked(True)

    def _on_view_extents(self) -> None:
        self.canvas_view.fit_to_content(margin=VIEW_EXTENTS_MARGIN)

    def _on_toggle_links_visible(self) -> None:
        self._links_visible = not self._links_visible
        if self.canvas_scene is not None:
            self.canvas_scene.set_links_visible(self._links_visible)
        self._update_toggle_links_action_text()
        self._update_links_status_label()

    def _update_toggle_links_action_text(self) -> None:
        self.toggle_links_action.setText("Hide Links" if self._links_visible else "Show Links")

    def _update_links_status_label(self) -> None:
        self.links_status_label.setText("Links: On" if self._links_visible else "Links: Off")

    def _on_toggle_emphasize_links(self, checked: bool) -> None:
        self._links_emphasized = checked
        if self.canvas_scene is not None:
            self.canvas_scene.set_links_emphasized(checked)

    def _on_change_link_weight(self, weight: int) -> None:
        if self.document is None or self.undo_stack is None:
            return
        old_weight = self.document.theme.link_weight
        if old_weight == weight:
            return
        self.undo_stack.push(ChangeLinkWeightCommand(self.document, old_weight, weight))

    def _update_line_weight_menu(self) -> None:
        if self.document is None:
            return
        weight = self.document.theme.link_weight
        for w, action in self._line_weight_actions.items():
            action.setChecked(w == weight)

    def _on_change_link_color_mode(self, mode: str) -> None:
        if self.document is None or self.undo_stack is None:
            return
        old_mode = self.document.theme.link_color_mode
        if old_mode == mode:
            return
        self.undo_stack.push(ChangeLinkColorModeCommand(self.document, old_mode, mode))

    def _update_line_color_menu(self) -> None:
        if self.document is None:
            return
        self._line_color_actions["theme"].setIcon(swatch_icon(self.document.theme.link_color))
        mode = self.document.theme.link_color_mode
        for m, action in self._line_color_actions.items():
            action.setChecked(m == mode)

    def _on_change_default_line_ending(self, line_ending: str) -> None:
        if self.document is None or self.undo_stack is None:
            return
        old_ending = self.document.default_line_ending
        if old_ending == line_ending:
            return
        self.undo_stack.push(
            ChangeDefaultLineEndingCommand(self.document, old_ending, line_ending)
        )

    def _update_default_line_ending_menu(self) -> None:
        if self.document is None:
            return
        ending = self.document.default_line_ending
        for value, action in self._default_line_ending_actions.items():
            action.setChecked(value == ending)

    def _on_change_line_endings(self, line_ending: str) -> None:
        if self.canvas_scene is None or self.document is None or self.undo_stack is None:
            return
        link_ids = self.canvas_scene.selected_link_ids()
        if not link_ids:
            return
        self.undo_stack.push(ChangeLinkLineEndingsCommand(self.document, link_ids, line_ending))

    def _update_line_endings_menu(self) -> None:
        if self.canvas_scene is None or self.document is None:
            self.link_line_endings_menu.menuAction().setEnabled(False)
            return
        link_ids = self.canvas_scene.selected_link_ids()
        self.link_line_endings_menu.menuAction().setEnabled(bool(link_ids))
        endings = {self.document.get_link(link_id).line_ending for link_id in link_ids}
        uniform_ending = next(iter(endings)) if len(endings) == 1 else None
        for value, action in self._line_ending_actions.items():
            action.setChecked(value == uniform_ending)

    def _on_toggle_color_key(self, checked: bool) -> None:
        if self.document is not None:
            self.document.set_color_key_visible(checked)

    def _on_select_all(self) -> None:
        if self.view_stack.currentWidget() is self.canvas_view:
            if self.canvas_scene is not None:
                self.canvas_scene.select_all_cards()
        else:
            self.list_view.table_view.selectAll()

    def _update_select_linked_enabled(self) -> None:
        focused = self.canvas_scene.selected_card_id() if self.canvas_scene is not None else None
        self.select_linked_action.setEnabled(focused is not None)

    def _on_select_linked(self) -> None:
        if self.canvas_scene is None:
            return
        card_id = self.canvas_scene.selected_card_id()
        if card_id is None:
            return
        item = self.canvas_scene.item_for_card(card_id)
        if item is None:
            return
        self.view_stack.setCurrentWidget(self.canvas_view)
        item.select_linked_graph()

    def _rebuild_add_to_stack_menu(self) -> None:
        """Rebuilds Edit > Add to Stack's contents on every aboutToShow —
        mirrors _rebuild_theme_list_section's approach, and mirrors
        CardItem._build_context_menu's own "Add to Stack" submenu exactly,
        since both ultimately dispatch through the same
        CardItem._create_new_stack_via_menu/_add_to_existing_stack."""
        for action in self._add_to_stack_dynamic_actions:
            self.add_to_stack_menu.removeAction(action)
            action.deleteLater()
        self._add_to_stack_dynamic_actions = []

        card_ids = self.canvas_scene.selected_card_ids() if self.canvas_scene is not None else []
        self.add_to_stack_menu.menuAction().setEnabled(bool(card_ids))
        if not card_ids or self.document is None:
            return

        new_stack_action = self.add_to_stack_menu.addAction("New Stack...")
        new_stack_action.triggered.connect(self._on_add_to_new_stack)
        self._add_to_stack_dynamic_actions.append(new_stack_action)

        if self.document.stacks:
            self._add_to_stack_dynamic_actions.append(self.add_to_stack_menu.addSeparator())
            for stack in self.document.iter_stacks():
                label = stack.label or f"Stack ({len(stack.card_ids)} cards)"
                action = self.add_to_stack_menu.addAction(label)
                action.triggered.connect(
                    lambda checked=False, stack_id=stack.id: self._on_add_to_existing_stack(
                        stack_id
                    )
                )
                self._add_to_stack_dynamic_actions.append(action)

    def _rebuild_card_color_menu(self) -> None:
        """Rebuilds Edit > Card Color's contents on every aboutToShow, same
        idiom as _rebuild_add_to_stack_menu -- necessary (not just a
        checked-state refresh) because the available colors themselves are
        per-theme and can change. Mirrors CardItem._build_context_menu's
        own "Color" submenu: same swatch icons, same "uniform selection
        color checked, mixed selection none checked" rule, and dispatches
        through the same ChangeColorsCommand-based apply path."""
        for action in self._card_color_dynamic_actions:
            self.card_color_menu.removeAction(action)
            action.deleteLater()
        self._card_color_dynamic_actions = []

        card_ids = self.canvas_scene.selected_card_ids() if self.canvas_scene is not None else []
        self.card_color_menu.menuAction().setEnabled(bool(card_ids))
        if not card_ids or self.document is None:
            return

        color_slots_in_selection = {self.document.get_card(cid).color_slot for cid in card_ids}
        uniform_slot = (
            next(iter(color_slots_in_selection)) if len(color_slots_in_selection) == 1 else None
        )
        group = QActionGroup(self)
        group.setExclusive(True)
        for slot in self.document.theme.slots:
            if slot.orphaned:
                continue
            action = self.card_color_menu.addAction(swatch_icon(slot.hex), slot.label)
            action.setCheckable(True)
            action.setChecked(slot.id == uniform_slot)
            action.triggered.connect(
                lambda checked=False, slot_id=slot.id: self._on_change_card_color(slot_id)
            )
            group.addAction(action)
            self._card_color_dynamic_actions.append(action)

    def _on_change_card_color(self, slot_id: str) -> None:
        if self.canvas_scene is None or self.document is None or self.undo_stack is None:
            return
        card_ids = self.canvas_scene.selected_card_ids()
        if not card_ids:
            return
        if all(self.document.get_card(cid).color_slot == slot_id for cid in card_ids):
            return
        self.undo_stack.push(ChangeColorsCommand(self.document, card_ids, slot_id))

    def _first_selected_canvas_item(self) -> CardItem | None:
        if self.canvas_scene is None:
            return None
        card_ids = self.canvas_scene.selected_card_ids()
        if not card_ids:
            return None
        return self.canvas_scene.item_for_card(card_ids[0])

    def _on_add_to_new_stack(self) -> None:
        item = self._first_selected_canvas_item()
        if item is not None:
            item._create_new_stack_via_menu()

    def _on_add_to_existing_stack(self, stack_id: str) -> None:
        item = self._first_selected_canvas_item()
        if item is not None:
            item._add_to_existing_stack(stack_id)

    def _update_remove_from_stack_action(self) -> None:
        overlay = self.canvas_view.stack_overlay
        self.remove_from_stack_action.setEnabled(
            overlay.is_open and overlay.selected_card_id is not None
        )

    def _on_remove_from_stack(self) -> None:
        overlay = self.canvas_view.stack_overlay
        if not overlay.is_open:
            return
        card_id = overlay.selected_card_id
        if card_id is not None:
            overlay.eject_card(card_id)

    def _update_view_extents_action_enabled(self) -> None:
        self.view_extents_action.setEnabled(not self.canvas_view.stack_overlay.is_open)

    def _update_pin_action(self) -> None:
        card_ids = self.canvas_scene.selected_card_ids() if self.canvas_scene is not None else []
        self.pin_action.setEnabled(bool(card_ids))
        noun = "Card" if len(card_ids) == 1 else "Card(s)"
        verb = "Unpin" if card_ids and self.document.all_pinned(card_ids) else "Pin"
        self.pin_action.setText(f"{verb} {noun}")

    def _on_toggle_pin(self) -> None:
        if self.canvas_scene is None or self.undo_stack is None:
            return
        card_ids = self.canvas_scene.selected_card_ids()
        if not card_ids:
            return
        pin = not self.document.all_pinned(card_ids)
        self.undo_stack.push(TogglePinCommand(self.document, card_ids, pin))

    def _update_delete_stack_action(self) -> None:
        stack_ids = self.canvas_scene.selected_stack_ids() if self.canvas_scene is not None else []
        self.delete_stack_action.setEnabled(bool(stack_ids))
        noun = "Stack" if len(stack_ids) == 1 else "Stacks"
        self.delete_stack_action.setText(f"Delete {noun}")

    def _on_delete_stack(self) -> None:
        if self.canvas_scene is None or self.undo_stack is None or self.document is None:
            return
        stack_ids = self.canvas_scene.selected_stack_ids()
        if not stack_ids:
            return

        confirmed_ids = []
        for stack_id in stack_ids:
            stack = self.document.get_stack(stack_id)
            if confirm_delete_stack(self, stack.label, len(stack.card_ids)):
                confirmed_ids.append(stack_id)
        if not confirmed_ids:
            return

        if len(confirmed_ids) == 1:
            push_delete_stack_and_cards(self.undo_stack, self.document, confirmed_ids[0])
            return

        # QUndoStack doesn't support nested macros, so — unlike the
        # single-stack case above — this inlines push_delete_stack_and_
        # cards's own per-stack pushes directly inside one outer macro
        # rather than calling it once per confirmed stack.
        self.undo_stack.beginMacro(f"Delete {len(confirmed_ids)} Stacks and Cards")
        for stack_id in confirmed_ids:
            member_ids = list(self.document.get_stack(stack_id).card_ids)
            for card_id in member_ids:
                self.undo_stack.push(DeleteCardCommand(self.document, card_id))
            self.undo_stack.push(RemoveStackCommand(self.document, stack_id))
        self.undo_stack.endMacro()

    def _on_gather_stacks(self) -> None:
        if self.document is None or self.undo_stack is None:
            return
        stacks = list(self.document.iter_stacks())
        if len(stacks) < 2:
            return

        card_positions = {
            card.id: (card.x, card.y)
            for card in self.document.iter_cards()
            if card.stack_id is None
        }
        cards_bbox = positions_bbox(card_positions) if card_positions else None
        new_positions = arrange_stacks_to_edge(
            stacks, self._settings.gather_stacks_edge, cards_bbox
        )
        old_positions = {stack.id: (stack.x, stack.y) for stack in stacks}
        self.undo_stack.push(GatherStacksCommand(self.document, old_positions, new_positions))
        self.canvas_view.ensure_content_visible()

    def _run_edges_arrange(self, mode: str) -> None:
        if self.document is None or self.undo_stack is None:
            return
        loose_cards = [card for card in self.document.iter_cards() if card.stack_id is None]
        stacks = list(self.document.iter_stacks())
        unpinned = [card for card in loose_cards if not card.pinned]
        if not unpinned and not stacks:
            return

        pinned_positions = {card.id: (card.x, card.y) for card in loose_cards if card.pinned}
        all_positions = {card.id: (card.x, card.y) for card in self.document.iter_cards()}
        all_positions.update({stack.id: (stack.x, stack.y) for stack in stacks})
        all_content_bbox = positions_bbox(all_positions) if all_positions else None

        viewport_size = self.canvas_view.viewport().size()
        aspect_ratio = (
            viewport_size.width() / viewport_size.height() if viewport_size.height() else 1.0
        )
        center_rect = compute_center_rect(pinned_positions, all_content_bbox, aspect_ratio)

        gather_edge = self._settings.gather_stacks_edge
        if mode == "tidy":
            new_card_positions = arrange_cards_tidy_to_edges(unpinned, center_rect, gather_edge)
        else:
            new_card_positions = arrange_cards_sweep_to_edges(unpinned, center_rect, gather_edge)

        old_card_positions = {
            card_id: (self.document.get_card(card_id).x, self.document.get_card(card_id).y)
            for card_id in new_card_positions
        }

        loose_card_positions = dict(pinned_positions)
        loose_card_positions.update(new_card_positions)
        cards_bbox = (
            union_bbox(positions_bbox(loose_card_positions), center_rect)
            if loose_card_positions
            else center_rect
        )
        new_stack_positions = arrange_stacks_to_edge(stacks, gather_edge, cards_bbox)
        old_stack_positions = {stack.id: (stack.x, stack.y) for stack in stacks}

        if not new_card_positions and not new_stack_positions:
            return

        label = "Tidy to Edges" if mode == "tidy" else "Sweep to Edges"
        self.undo_stack.beginMacro(label)
        if new_card_positions:
            self.undo_stack.push(
                AutoArrangeCommand(self.document, old_card_positions, new_card_positions)
            )
        if new_stack_positions:
            self.undo_stack.push(
                GatherStacksCommand(self.document, old_stack_positions, new_stack_positions)
            )
        self.undo_stack.endMacro()
        self.canvas_view.ensure_content_visible()

    def _on_new(self) -> None:
        if self._window_manager is not None:
            self._window_manager.open_new_window()
        else:
            self._set_document(
                Document(
                    name="Untitled",
                    theme=resolve_default_theme(self._settings, self._theme_library),
                ),
                path=None,
            )

    def _on_open(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(self, "Open File", "", FILE_DIALOG_FILTER)
        if not path_str:
            return
        path = Path(path_str)
        if self._window_manager is not None:
            self._window_manager.open_file(path, requesting_window=self)
        else:
            self.open_file(path)

    def _on_save(self) -> None:
        if self.document is None:
            return
        if self._current_path is None:
            self._on_save_as()
            return
        self._save_to(self._current_path)

    def _on_save_as(self) -> None:
        if self.document is None:
            return
        default_name = f"{self.document.name}.idxcards"
        path_str, _ = QFileDialog.getSaveFileName(
            self, "Save File As", default_name, FILE_DIALOG_FILTER
        )
        if not path_str:
            return
        path = Path(path_str)
        if path.suffix != ".idxcards":
            path = path.with_suffix(".idxcards")
        self._save_to(path)

    def _save_to(self, path: Path) -> None:
        # Captured directly onto the document (not through a mutator/signal
        # -- see Document.view_zoom's own comment) so "View from last save"
        # has something to restore next time this file is opened.
        center = self.canvas_view.mapToScene(self.canvas_view.viewport().rect().center())
        self.document.view_zoom = self.canvas_view.zoom
        self.document.view_center_x = center.x()
        self.document.view_center_y = center.y()
        # Keeps the window title (and this file's own name if reopened
        # later) matching whatever it's actually being saved as -- see
        # _set_document's identical sync on open for the fuller rationale.
        self.document.name = path.stem
        try:
            save_document(self.document, path)
        except OSError as exc:
            QMessageBox.critical(self, "Failed to Save File", str(exc))
            return
        self._current_path = path
        self.undo_stack.setClean()
        self._update_title()

    @property
    def current_path(self) -> Path | None:
        return self._current_path

    def is_reusable(self) -> bool:
        """True for a blank, untouched Untitled window — no file path, no
        edits — the state File > Open should replace rather than leaving
        stranded as an extra empty window."""
        return self._current_path is None and (
            self.undo_stack is None or self.undo_stack.isClean()
        )

    def open_file(self, path: Path) -> None:
        try:
            document = load_document(path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Failed to Open File", str(exc))
            return
        if document.load_warnings:
            # Purely informational -- the file is already loaded and usable;
            # this just tells a human what got silently corrected (e.g. a
            # dangling reference in a hand-authored/agent-generated file)
            # instead of leaving them to notice something looks off later.
            QMessageBox.warning(
                self,
                "File Repaired on Open",
                "This file had some issues that were automatically fixed:\n\n"
                + "\n".join(document.load_warnings),
            )
        self._set_document(document, path)
        # Deferred: a freshly-created window's viewport still has a
        # meaningless placeholder size at this point (WindowManager.open_file
        # calls this before window.show()) -- confirmed empirically, not
        # just assumed. By the next event-loop tick, any show() the caller
        # runs synchronously right after this method returns has already
        # happened, so the viewport has its real, final geometry.
        QTimer.singleShot(0, self._apply_initial_view)

    def _apply_initial_view(self) -> None:
        if self.document is None:
            return
        if (
            self._settings.view_on_open == "last_save"
            and self.document.view_zoom is not None
            and self.document.view_center_x is not None
            and self.document.view_center_y is not None
        ):
            self.canvas_view.restore_view_state(
                self.document.view_zoom, self.document.view_center_x, self.document.view_center_y
            )
        else:
            self.canvas_view.center_or_fit_to_content()

    def _set_document(self, document: Document, path: Path | None) -> None:
        old_stack = self.undo_stack
        old_model = self.card_table_model
        old_scene = self.canvas_scene

        self.undo_stack = QUndoStack(self)
        self._undo_group.addStack(self.undo_stack)
        self._activate_undo_stack()

        self.document = document
        self._current_path = path
        if path is not None:
            # Keeps the window title (and Save As's default filename, and
            # the unsaved-changes dialog) in sync with the file actually on
            # disk -- document.name has no in-app way to be set otherwise,
            # so without this it stays whatever it was when the document
            # was first created (typically "Untitled") no matter what the
            # file gets saved or opened as. Not a mutator/signal call: name
            # is plain, non-reactive state (like created_at/modified_at),
            # and this must not dirty a document that was just opened.
            document.name = path.stem
        self.toggle_color_key_action.setChecked(document.color_key_visible)
        self.card_table_model = CardTableModel(document, undo_stack=self.undo_stack, parent=self)
        self.list_view.set_model(self.card_table_model)
        self.canvas_scene = CanvasScene(document, undo_stack=self.undo_stack, parent=self)
        self.canvas_scene.set_search_query(self._current_search_query)
        self.canvas_scene.set_links_visible(self._links_visible)
        self.canvas_scene.set_links_emphasized(self._links_emphasized)
        self.canvas_view.setScene(self.canvas_scene)
        self.canvas_scene.selectionChanged.connect(self._on_canvas_selection_changed)
        self.undo_stack.cleanChanged.connect(self._update_title)
        self._update_title()
        self._update_arrange_actions_enabled()
        # Without this, a freshly opened/created window's Cut/Copy/Paste
        # shortcuts stay stuck at whatever _build_menu()'s one-time check
        # found (self.document was still None then, so paste_action was
        # forced disabled regardless of what's actually on the clipboard)
        # until some later selection/clipboard-change signal happens to
        # fire — e.g. the user opening the Edit menu once. A new window
        # opened via Cmd+N after copying something elsewhere should be
        # paste-ready immediately, not just after the menu's first open.
        self._update_clipboard_actions_enabled()

        if old_model is not None:
            old_model.deleteLater()
        if old_scene is not None:
            old_scene.deleteLater()
        if old_stack is not None:
            old_stack.deleteLater()

    def _on_list_current_card_changed(self, card_id: str | None) -> None:
        if self._syncing_selection:
            return
        self._syncing_selection = True
        try:
            self._select_card_in_canvas(card_id)
        finally:
            self._syncing_selection = False

    def _on_canvas_selection_changed(self) -> None:
        self._update_clipboard_actions_enabled()
        card_id = self.canvas_scene.selected_card_id()
        if card_id is not None and card_id not in self.document.cards:
            # A cascading delete can fire selectionChanged (e.g. removing a
            # selected LinkItem) before the still-selected CardItem's own
            # cardRemoved signal has run — the item is still in the scene,
            # selected, but the Document has already dropped its data.
            card_id = None
        if self._syncing_selection:
            return
        self._syncing_selection = True
        try:
            self._select_card_in_list(card_id)
        finally:
            self._syncing_selection = False

    def _select_card_in_canvas(self, card_id: str | None) -> None:
        for item in self.canvas_scene.selectedItems():
            item.setSelected(False)
        if card_id is not None:
            item = self.canvas_scene.item_for_card(card_id)
            if item is not None:
                item.setSelected(True)

    def _select_card_in_list(self, card_id: str | None) -> None:
        table_view = self.list_view.table_view
        if card_id is None:
            table_view.clearSelection()
            table_view.setCurrentIndex(QModelIndex())
            return
        row = self.card_table_model.row_for_card_id(card_id)
        if row is None:
            return
        proxy_index = self.list_view.proxy_model.mapFromSource(self.card_table_model.index(row, 0))
        if not proxy_index.isValid():
            return  # filtered out by the current search query
        table_view.selectRow(proxy_index.row())

    def _focus_search_bar(self) -> None:
        self.search_bar.line_edit.setFocus()
        self.search_bar.line_edit.selectAll()

    def _on_create_card_shortcut(self) -> None:
        if self.canvas_view.stack_overlay.is_open:
            # Blocks canvas interaction while a Stack overlay is open,
            # same convention as wheel/pan and pinch-zoom -- the new card
            # goes straight into the open stack instead.
            self.canvas_view.stack_overlay.create_card()
            return
        if self.card_table_model is None:
            return
        card_id = self.card_table_model.add_card()
        self._select_and_focus_new_card(card_id)

    def _select_and_focus_new_card(self, card_id: str | None) -> None:
        if card_id is None:
            return
        self._select_card_in_list(card_id)
        if self.view_stack.currentWidget() is self.canvas_view:
            item = self.canvas_scene.item_for_card(card_id) if self.canvas_scene else None
            if item is not None:
                item.enter_edit_mode()
        else:
            self.list_view.edit_text_cell(card_id)

    def _on_search_query_changed(self, query: str) -> None:
        self._current_search_query = query
        self.list_view.set_search_query(query)
        if self.canvas_scene is not None:
            self.canvas_scene.set_search_query(query)

    def _on_link_requested(self, source_id: str, target_id: str) -> None:
        if self.document is None or self.undo_stack is None:
            return
        link_id = new_link_id(self.document.links.keys())
        link = Link(
            id=link_id,
            source=source_id,
            target=target_id,
            line_ending=self.document.default_line_ending,
        )
        self.undo_stack.push(AddLinkCommand(self.document, link))

    def _on_canvas_delete_requested(self) -> None:
        if self.canvas_scene is None or self.undo_stack is None or self.document is None:
            return
        card_ids = self.canvas_scene.selected_card_ids()
        link_ids = self.canvas_scene.selected_link_ids()

        incident_link_count = 0
        if card_ids:
            card_id_set = set(card_ids)
            incident_link_ids = {
                link.id
                for link in self.document.links.values()
                if link.source in card_id_set or link.target in card_id_set
            }
            # Cards being deleted cascade their own incident links, so drop
            # those from the explicit link-deletion list to avoid deleting
            # the same link twice (the second delete would raise a KeyError).
            link_ids = [link_id for link_id in link_ids if link_id not in incident_link_ids]
            incident_link_count = len(incident_link_ids)
            if not confirm_delete_cards(self, len(card_ids), incident_link_count, self._settings):
                return

        if not card_ids and not link_ids:
            return

        total = len(card_ids) + len(link_ids)
        if total == 1:
            if card_ids:
                self.undo_stack.push(DeleteCardCommand(self.document, card_ids[0]))
            else:
                self.undo_stack.push(DeleteLinkCommand(self.document, link_ids[0]))
            return

        self.undo_stack.beginMacro(f"Delete {total} Item(s)")
        for card_id in card_ids:
            self.undo_stack.push(DeleteCardCommand(self.document, card_id))
        for link_id in link_ids:
            self.undo_stack.push(DeleteLinkCommand(self.document, link_id))
        self.undo_stack.endMacro()

    def _clipboard(self) -> QClipboard:
        return QApplication.clipboard()

    def _active_selection(self) -> tuple[list[str], list[str]]:
        """(card_ids, stack_ids) from whichever view currently has
        selection/focus — canvas (cards + stacks) or List view (cards
        only; it has no stack concept)."""
        if self.canvas_scene is not None and self.view_stack.currentWidget() is self.canvas_view:
            return self.canvas_scene.selected_card_ids(), self.canvas_scene.selected_stack_ids()
        return self.list_view.selected_card_ids(), []

    def _update_clipboard_actions_enabled(self) -> None:
        card_ids, stack_ids = self._active_selection() if self.document is not None else ([], [])
        has_selection = bool(card_ids or stack_ids)
        self.cut_action.setEnabled(has_selection)
        self.copy_action.setEnabled(has_selection)

        mime = self._clipboard().mimeData()
        self.paste_action.setEnabled(
            self.document is not None
            and mime is not None
            and (mime.hasFormat(CLIPBOARD_MIME_TYPE) or mime.hasText())
        )

    def _copy_to_clipboard(self, card_ids: list[str], stack_ids: list[str]) -> None:
        payload = build_clipboard_payload(self.document, card_ids, stack_ids)
        mime = QMimeData()
        mime.setText(plain_text_for_payload(payload, normalize_text=_card_text_to_logical))
        mime.setData(CLIPBOARD_MIME_TYPE, QByteArray(json.dumps(payload).encode("utf-8")))
        self._clipboard().setMimeData(mime)
        # The real QClipboard's dataChanged signal (connected in
        # _build_menu) already keeps paste_action live for this — this
        # direct call is what makes it immediate in tests, where the fake
        # clipboard used to isolate them from the real one has no such
        # signal to fire.
        self._update_clipboard_actions_enabled()

    def _on_copy(self) -> None:
        if self.document is None:
            return
        card_ids, stack_ids = self._active_selection()
        if not card_ids and not stack_ids:
            return
        self._copy_to_clipboard(card_ids, stack_ids)

    def _on_cut(self) -> None:
        if self.document is None or self.undo_stack is None:
            return
        card_ids, stack_ids = self._active_selection()
        if not card_ids and not stack_ids:
            return
        self._copy_to_clipboard(card_ids, stack_ids)

        total = len(card_ids) + len(stack_ids)
        if total == 1:
            if card_ids:
                self.undo_stack.push(DeleteCardCommand(self.document, card_ids[0]))
            else:
                push_delete_stack_and_cards(self.undo_stack, self.document, stack_ids[0])
            return

        # QUndoStack doesn't support nested macros, so — mirroring
        # _on_delete_stack's own multi-stack branch — this inlines
        # push_delete_stack_and_cards's per-stack pushes directly inside
        # one outer macro rather than calling it once per stack.
        self.undo_stack.beginMacro(f"Cut {total} Item(s)")
        for card_id in card_ids:
            self.undo_stack.push(DeleteCardCommand(self.document, card_id))
        for stack_id in stack_ids:
            member_ids = list(self.document.get_stack(stack_id).card_ids)
            for member_id in member_ids:
                self.undo_stack.push(DeleteCardCommand(self.document, member_id))
            self.undo_stack.push(RemoveStackCommand(self.document, stack_id))
        self.undo_stack.endMacro()

    def _on_paste(self) -> None:
        if self.document is None or self.undo_stack is None:
            return
        mime = self._clipboard().mimeData()
        if mime is None:
            return

        cards: list[Card] = []
        stacks: list[tuple[Stack, list[Card]]] = []

        if mime.hasFormat(CLIPBOARD_MIME_TYPE):
            try:
                payload = json.loads(bytes(mime.data(CLIPBOARD_MIME_TYPE)).decode("utf-8"))
                existing_ids = set(self.document.cards) | set(self.document.stacks)
                cards, stacks = cards_and_stacks_from_payload(
                    payload, self.document.theme, existing_ids
                )
            except (ValueError, UnicodeDecodeError):
                cards, stacks = [], []

        if not cards and not stacks and mime.hasText():
            texts = card_texts_from_plain_text(
                mime.text(), denormalize_text=_logical_text_to_card_text
            )
            if texts:
                existing_ids = set(self.document.cards)
                default_slot = self.document.theme.slots[0].id
                new_cards = []
                for text in texts:
                    card_id = new_card_id(existing_ids)
                    existing_ids.add(card_id)
                    new_cards.append(Card(id=card_id, text=text, color_slot=default_slot))
                tile_positions = arrange_by_tile(new_cards)
                for card in new_cards:
                    card.x, card.y = tile_positions[card.id]
                cards = new_cards

        if not cards and not stacks:
            return

        positions = {card.id: (card.x, card.y) for card in cards}
        positions.update({stack.id: (stack.x, stack.y) for stack, _members in stacks})
        source_bbox = positions_bbox(positions)
        source_center = (
            (source_bbox[0] + source_bbox[2]) / 2,
            (source_bbox[1] + source_bbox[3]) / 2,
        )
        target_center = self.canvas_view.mapToScene(self.canvas_view.viewport().rect().center())
        dx = target_center.x() - source_center[0]
        dy = target_center.y() - source_center[1]

        for card in cards:
            card.x += dx
            card.y += dy
        for stack, members in stacks:
            stack.x += dx
            stack.y += dy
            for member in members:
                member.x += dx
                member.y += dy

        # Repeated pastes of the same clipboard content would otherwise
        # all recenter to the exact same spot, perfectly overlapping each
        # other and whatever's already there — nudge each new card/stack
        # diagonally, in turn, until it's substantially clear of every
        # existing loose card/stack and everything already placed earlier
        # in this same paste.
        obstacles = [
            (c.x, c.y) for c in self.document.iter_cards() if c.stack_id is None
        ] + [(s.x, s.y) for s in self.document.iter_stacks()]
        for card in cards:
            card.x, card.y = avoid_card_overlap((card.x, card.y), obstacles)
            obstacles.append((card.x, card.y))
        for stack, _members in stacks:
            stack.x, stack.y = avoid_card_overlap((stack.x, stack.y), obstacles)
            obstacles.append((stack.x, stack.y))

        push_paste(self.undo_stack, self.document, cards, stacks)

    def _update_arrange_actions_enabled(self) -> None:
        unstacked_unpinned_count = (
            sum(
                1
                for card in self.document.iter_cards()
                if not card.pinned and card.stack_id is None
            )
            if self.document is not None
            else 0
        )
        enabled = unstacked_unpinned_count >= 2
        self.arrange_tile_action.setEnabled(enabled)
        self.arrange_scatter_action.setEnabled(enabled)
        self.arrange_columns_by_color_action.setEnabled(enabled)
        self.arrange_columns_alphabetical_action.setEnabled(enabled)
        self.arrange_columns_menu.menuAction().setEnabled(enabled)

        stack_count = len(self.document.stacks) if self.document is not None else 0
        self.gather_stacks_action.setEnabled(stack_count >= 2)

        edges_enabled = unstacked_unpinned_count >= 1 or stack_count >= 1
        self.tidy_to_edges_action.setEnabled(edges_enabled)
        self.sweep_to_edges_action.setEnabled(edges_enabled)

        # Distinct from unstacked_unpinned_count above: two eligible loose
        # cards that aren't actually linked to each other wouldn't do
        # anything different than Tile, so this only lights up when
        # there's a real graph for it to spread out. Pinned status is
        # deliberately not part of this check -- Untangle Links is the
        # one arrange action that ignores it.
        untangleable = False
        if self.document is not None:
            for link in self.document.links.values():
                source = self.document.cards.get(link.source)
                target = self.document.cards.get(link.target)
                if source is not None and target is not None:
                    if source.stack_id is None and target.stack_id is None:
                        untangleable = True
                        break
        self.untangle_links_action.setEnabled(untangleable)

    def _run_auto_arrange(self, group_by: str) -> None:
        if self.document is None or self.undo_stack is None:
            return
        cards = [card for card in self.document.iter_cards() if card.stack_id is None]
        if not cards or all(card.pinned for card in cards):
            return

        viewport_size = self.canvas_view.viewport().size()
        aspect_ratio = (
            viewport_size.width() / viewport_size.height() if viewport_size.height() else 1.0
        )
        overflow_limit = (
            self._settings.arrange_column_limit if self._settings.limit_arrange_columns else None
        )
        stack_positions = {
            stack.id: (stack.x, stack.y) for stack in self.document.iter_stacks()
        }
        new_positions = arrange_avoiding_obstacles(
            cards,
            group_by,
            aspect_ratio=aspect_ratio,
            overflow_limit=overflow_limit,
            theme=self.document.theme,
            stack_positions=stack_positions,
        )
        if not new_positions:
            return
        old_positions = {
            card_id: (self.document.get_card(card_id).x, self.document.get_card(card_id).y)
            for card_id in new_positions
        }
        self.undo_stack.push(AutoArrangeCommand(self.document, old_positions, new_positions))
        self.canvas_view.ensure_content_visible()

    def _run_untangle_links(self) -> None:
        """With a canvas selection that actually touches a real link
        graph, reflows just the component(s) touched by that selection,
        in place -- everything else on the canvas (other graphs, loose
        cards) is left untouched. Otherwise (no selection, or a
        selection that doesn't touch any link) falls back to the
        whole-document behavior: every real graph gets its own
        force-directed layout, packed side by side, with every isolated
        card tiled into its own block alongside them.

        Unlike every other Arrange action, pinned status is ignored
        entirely -- a pinned card can be part of a tangled graph same as
        any other, and untangling it is a targeted request, not the
        kind of bulk reorganization pinning is meant to protect against.
        This is also why the whole-document fallback below calls
        arrange_by_untangle_links directly rather than going through
        arrange_avoiding_obstacles like every other arrange mode: that
        wrapper's whole job is excluding pinned cards, which is exactly
        the one thing this mode doesn't want. Stack boxes are still
        avoided -- shift_layout_to_clear is the same primitive
        arrange_avoiding_obstacles itself uses internally."""
        if self.document is None or self.undo_stack is None or self.canvas_scene is None:
            return
        cards = list(self.document.iter_cards())
        links = list(self.document.links.values())

        selected_ids = self.canvas_scene.selected_card_ids()
        new_positions = (
            arrange_untangle_touching(selected_ids, cards, links) if selected_ids else {}
        )

        if not new_positions:
            loose_cards = [card for card in cards if card.stack_id is None]
            if not loose_cards:
                return
            viewport_size = self.canvas_view.viewport().size()
            aspect_ratio = (
                viewport_size.width() / viewport_size.height() if viewport_size.height() else 1.0
            )
            new_positions = arrange_by_untangle_links(loose_cards, links, aspect_ratio)
            stack_positions = {
                stack.id: (stack.x, stack.y) for stack in self.document.iter_stacks()
            }
            if stack_positions:
                new_positions = shift_layout_to_clear(
                    new_positions, stack_positions, ARRANGE_AVOIDANCE_GUTTER
                )
        if not new_positions:
            return

        old_positions = {
            card_id: (self.document.get_card(card_id).x, self.document.get_card(card_id).y)
            for card_id in new_positions
        }
        self.undo_stack.push(AutoArrangeCommand(self.document, old_positions, new_positions))
        self.canvas_view.ensure_content_visible()

    def _on_change_canvas_background(self) -> None:
        if self.document is None or self.undo_stack is None:
            return
        old_color = self.document.canvas_background_color
        chosen = QColorDialog.getColor(QColor(old_color), self, "Canvas Background Color")
        if not chosen.isValid():
            return
        new_color = chosen.name()
        if new_color.lower() == old_color.lower():
            return
        self.undo_stack.push(ChangeCanvasBackgroundCommand(self.document, old_color, new_color))

    def _on_edit_current_theme(self) -> None:
        if self.document is None or self.undo_stack is None:
            return
        dialog = ThemeEditorDialog(self.document.theme, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        new_theme, newly_orphaned = self.document.plan_theme_edit(dialog.result_theme())
        self.undo_stack.push(SetDocumentThemeCommand(self.document, self.document.theme, new_theme))
        if newly_orphaned:
            QMessageBox.warning(
                self,
                "Some Colors Are No Longer In This Theme",
                "Cards using a color you removed will keep that color, "
                "marked as orphaned, until it's resolved.",
            )
            self._open_orphan_resolution(newly_orphaned)

    def _rebuild_theme_list_section(self) -> None:
        """Rebuilds the Theme menu's list of available themes (presets
        first, then the library's custom themes) — called on every
        aboutToShow rather than kept live, since it only needs to be
        correct while the menu is actually open: the current theme (for
        the checkmark) can change via undo/redo, and the custom theme
        list can grow via Duplicate, neither of which this menu is
        otherwise watching for."""
        for action in self._theme_list_actions:
            self._theme_menu.removeAction(action)
            self._theme_list_group.removeAction(action)
            action.deleteLater()
        self._theme_list_actions = []
        if self.document is None:
            return
        current_theme_id = self.document.theme.id
        for theme in [*PRESET_THEMES, *self._theme_library.all()]:
            action = QAction(theme.name, self)
            action.setCheckable(True)
            action.setChecked(theme.id == current_theme_id)
            action.triggered.connect(lambda _checked=False, t=theme: self._on_select_theme(t))
            self._theme_list_group.addAction(action)
            self._theme_menu.insertAction(self._theme_list_separator, action)
            self._theme_list_actions.append(action)

    def _on_select_theme(self, theme: Theme) -> None:
        if self.document is None or self.undo_stack is None or theme.id == self.document.theme.id:
            return
        new_theme, newly_orphaned, color_slot_remap = self.document.plan_theme_switch(theme)
        self.undo_stack.push(
            SetDocumentThemeCommand(
                self.document, self.document.theme, new_theme, color_slot_remap
            )
        )
        if newly_orphaned:
            QMessageBox.warning(
                self,
                "Some Colors Aren't In The New Theme",
                "Cards using a color the new theme doesn't have will keep "
                "that color, marked as orphaned, until it's resolved.",
            )
            self._open_orphan_resolution(newly_orphaned)

    def _on_duplicate_current_theme(self) -> None:
        if self.document is None:
            return
        name, ok = QInputDialog.getText(
            self,
            "Duplicate Theme",
            "New theme name:",
            text=f"{self.document.theme.name} Copy",
        )
        if not ok or not name.strip():
            return
        new_theme = duplicate_theme(self.document.theme, new_theme_id(), name.strip())
        self._theme_library.add(new_theme)

    def _open_orphan_resolution(self, orphan_slot_ids: list[str]) -> None:
        """Shared by both orphan-producing triggers (editing the current
        theme, switching to a different one) and by the standing
        "Resolve Orphaned Colors…" action — resolution can be deferred
        past the initial warning and revisited later, not just handled
        synchronously at the moment an orphan is created."""
        if self.document is None or self.undo_stack is None:
            return
        dialog = OrphanResolutionDialog(self.document, orphan_slot_ids, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.undo_stack.beginMacro("Resolve Orphaned Colors")
        for slot_id, target_slot_id in dialog.resolutions():
            if target_slot_id is None:
                self.undo_stack.push(KeepOrphanColorCommand(self.document, slot_id))
            else:
                self.undo_stack.push(
                    ReassignOrphanColorCommand(self.document, slot_id, target_slot_id)
                )
        self.undo_stack.endMacro()

    def _on_resolve_orphaned_colors(self) -> None:
        if self.document is None:
            return
        orphan_slot_ids = [slot.id for slot in self.document.theme.slots if slot.orphaned]
        if not orphan_slot_ids:
            return
        self._open_orphan_resolution(orphan_slot_ids)

    def _update_resolve_orphaned_colors_enabled(self) -> None:
        has_orphans = self.document is not None and any(
            slot.orphaned for slot in self.document.theme.slots
        )
        self.resolve_orphaned_colors_action.setEnabled(has_orphans)

    def _on_open_settings(self) -> None:
        available_themes = [*PRESET_THEMES, *self._theme_library.all()]
        dialog = SettingsDialog(
            self._settings.warn_before_delete,
            self._settings.default_theme_id,
            available_themes,
            self._settings.limit_arrange_columns,
            self._settings.arrange_column_limit,
            self._settings.gather_stacks_edge,
            self._settings.view_on_open,
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._settings.warn_before_delete = dialog.warn_before_delete()
        self._settings.default_theme_id = dialog.default_theme_id()
        self._settings.limit_arrange_columns = dialog.limit_arrange_columns()
        self._settings.arrange_column_limit = dialog.arrange_column_limit()
        self._settings.gather_stacks_edge = dialog.gather_stacks_edge()
        self._settings.view_on_open = dialog.view_on_open()

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        is_key_event = event.type() in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease)
        if is_key_event and not event.isAutoRepeat() and event.key() == Qt.Key.Key_Alt:
            if event.type() == QEvent.Type.KeyPress:
                if self.isActiveWindow():
                    self.canvas_view.link_controller.set_active(True)
            else:
                # Always deactivate on release, even if this window isn't
                # the active one right now — otherwise a window that lost
                # activation mid-hold (see changeEvent) could never get the
                # matching release to clear on its own.
                self.canvas_view.link_controller.set_active(False)
        return super().eventFilter(watched, event)

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.ActivationChange:
            if self.isActiveWindow():
                self._activate_undo_stack()
            else:
                # Guards against Link Mode getting stuck on: if the user
                # holds Option and switches away (Cmd-Tab, another window),
                # this app never sees the matching key-release event.
                self.canvas_view.link_controller.set_active(False)

    def _activate_undo_stack(self) -> None:
        if self.undo_stack is not None:
            self._undo_group.setActiveStack(self.undo_stack)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.undo_stack is not None and not self.undo_stack.isClean():
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                f"'{self.document.name}' has unsaved changes. Save before closing?",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if reply == QMessageBox.StandardButton.Save:
                self._on_save()
                if not self.undo_stack.isClean():
                    # Save As was cancelled, or the save failed; don't close.
                    event.ignore()
                    return

        QApplication.instance().removeEventFilter(self)
        if self._window_manager is not None:
            self._window_manager.forget_window(self)
        event.accept()

    def _update_title(self) -> None:
        if self.document is None:
            self.setWindowTitle("Index Cards")
            return
        dirty_marker = "" if self.undo_stack.isClean() else "*"
        self.setWindowTitle(f"Index Cards — {self.document.name}{dirty_marker}")
