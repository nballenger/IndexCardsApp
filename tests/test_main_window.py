import json
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QMimeData, QPointF, Qt
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QColor,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QTextCursor,
    QTextDocument,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QColorDialog,
    QDialog,
    QFileDialog,
    QInputDialog,
    QMessageBox,
)

from indexcards.app_settings import AppSettings
from indexcards.arrange.auto_arrange import _max_overlap_fraction, positions_bbox
from indexcards.canvas.canvas_view import VIEW_EXTENTS_MARGIN
from indexcards.canvas.link_item import LinkItem
from indexcards.list_view.card_table_model import COLUMN_COLOR, COLUMN_TAGS, COLUMN_TEXT
from indexcards.main_window import MainWindow, _ClickableLabel
from indexcards.models.card import Card
from indexcards.models.document import Document
from indexcards.models.link import Link
from indexcards.models.presets import PRESET_THEMES, get_preset_theme
from indexcards.models.stack import Stack
from indexcards.models.theme import Slot, Theme, clone_theme
from indexcards.persistence.file_io import load_document, save_document
from indexcards.utils.clipboard_format import CLIPBOARD_MIME_TYPE
from indexcards.widgets.orphan_resolution_dialog import OrphanResolutionDialog
from indexcards.widgets.settings_dialog import SettingsDialog
from indexcards.window_manager import WindowManager

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample.idxcards"


def test_main_window_has_file_menu(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.windowTitle() == "Index Cards — Untitled"
    menu_titles = [action.text() for action in window.menuBar().actions()]
    assert "&File" in menu_titles
    assert "&Edit" in menu_titles


def test_open_file_populates_list_view(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window.open_file(FIXTURE_PATH)

    # document.name is synced to the opened file's own filename stem (see
    # MainWindow._set_document) -- not "Sample Fixture", the fixture's
    # internal file.name, which no in-app action can ever set anyway.
    assert window.windowTitle() == "Index Cards — sample"
    model = window.card_table_model
    assert model.rowCount() == 3
    expected_text = "**Working title**\n\nA story about *time* and index cards."
    assert model.index(0, COLUMN_TEXT).data() == expected_text
    assert model.index(0, COLUMN_COLOR).data() == "#F6E27A"
    assert model.index(0, COLUMN_TAGS).data() == "plot, urgent"
    assert model.index(1, COLUMN_TAGS).data() == ""

    assert window.canvas_view.scene() is window.canvas_scene
    # 3 cards + 1 link from the fixture; each CardItem also owns a child
    # text item for in-place editing, so filter down to top-level items.
    top_level_items = [item for item in window.canvas_scene.items() if item.parentItem() is None]
    assert len(top_level_items) == 4
    item = window.canvas_scene.item_for_card("c_4f9a1b2c")
    assert (item.pos().x(), item.pos().y()) == (120.0, 340.0)


def test_open_missing_file_shows_error_without_crashing(qtbot, monkeypatch):
    import indexcards.main_window as main_window_module

    shown_messages = []
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "critical",
        lambda *args, **kwargs: shown_messages.append(args),
    )

    window = MainWindow()
    qtbot.addWidget(window)
    original_document = window.document

    window.open_file(Path("/nonexistent/path/does_not_exist.idxcards"))

    assert window.document is original_document
    assert len(shown_messages) == 1


def test_edit_via_model_marks_dirty_and_undo_clears_it(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)

    index = window.card_table_model.index(0, COLUMN_TEXT)
    window.card_table_model.setData(index, "edited text")

    assert window.undo_stack.isClean() is False
    assert window.windowTitle() == "Index Cards — sample*"

    window.undo_stack.undo()

    assert window.undo_stack.isClean() is True
    assert window.windowTitle() == "Index Cards — sample"


def test_save_as_to_a_new_name_updates_document_name_and_does_not_dirty(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)
    assert window.document.name == "sample"

    save_path = tmp_path / "My Board.idxcards"
    window._save_to(save_path)

    assert window.document.name == "My Board"
    assert window.windowTitle() == "Index Cards — My Board"
    assert window.document.dirty is False

    reloaded = load_document(save_path)
    assert reloaded.name == "My Board"


def test_opening_a_file_syncs_document_name_even_if_saved_content_disagrees(qtbot, tmp_path):
    # The saved file.name is a stale/hand-edited value different from the
    # actual filename -- opening it must still show the real filename, not
    # whatever the JSON happens to claim.
    document = Document(name="Some Other Title Entirely")
    document.add_card(Card(id="c_1"))
    path = tmp_path / "renamed.idxcards"
    save_document(document, path)

    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(path)

    assert window.document.name == "renamed"
    assert window.windowTitle() == "Index Cards — renamed"


def test_save_writes_file_and_clears_dirty(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)

    index = window.card_table_model.index(0, COLUMN_TEXT)
    window.card_table_model.setData(index, "edited text")
    assert window.document.dirty is True

    save_path = tmp_path / "saved.idxcards"
    window._save_to(save_path)

    assert window.document.dirty is False
    # document.name is synced to the save path's own filename stem.
    assert window.windowTitle() == "Index Cards — saved"

    reloaded = load_document(save_path)
    assert reloaded.get_card("c_4f9a1b2c").text == "edited text"


def test_new_replaces_document_with_fresh_undo_stack(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)

    index = window.card_table_model.index(0, COLUMN_TEXT)
    window.card_table_model.setData(index, "edited text")
    assert window.undo_stack.canUndo() is True

    window._on_new()

    assert window.document.name == "Untitled"
    assert window.card_table_model.rowCount() == 0
    assert window.undo_stack.canUndo() is False
    assert window.windowTitle() == "Index Cards — Untitled"


def test_list_selection_selects_matching_card_on_canvas(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)

    source_index = window.card_table_model.index(0, COLUMN_TEXT)
    proxy_index = window.list_view.proxy_model.mapFromSource(source_index)
    window.list_view.table_view.setCurrentIndex(proxy_index)

    item = window.canvas_scene.item_for_card("c_4f9a1b2c")
    assert item.isSelected()


def test_canvas_selection_selects_matching_row_in_list(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)

    item = window.canvas_scene.item_for_card("c_7bd310aa")
    item.setSelected(True)

    row = window.card_table_model.row_for_card_id("c_7bd310aa")
    selected_rows = {
        index.row() for index in window.list_view.table_view.selectionModel().selectedRows()
    }
    assert selected_rows == {row}


def test_editing_card_text_on_canvas_updates_list_view_and_undo_works(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)

    item = window.canvas_scene.item_for_card("c_4f9a1b2c")
    item.enter_edit_mode()
    cursor = item._text_item.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    cursor.insertText("Edited on canvas")
    item._on_text_focus_out()

    assert "Edited on canvas" in window.card_table_model.index(0, COLUMN_TEXT).data()
    assert window.undo_stack.canUndo()

    window.undo_stack.undo()
    assert "Working title" in window.card_table_model.index(0, COLUMN_TEXT).data()


def test_selecting_card_on_canvas_selects_matching_row_in_list(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)

    item = window.canvas_scene.item_for_card("c_1a2b3c4d")
    item.setSelected(True)

    row = window.card_table_model.row_for_card_id("c_1a2b3c4d")
    selected_rows = {
        index.row() for index in window.list_view.table_view.selectionModel().selectedRows()
    }
    assert selected_rows == {row}
    assert "Untagged loose thought" in window.card_table_model.index(row, COLUMN_TEXT).data()


def test_selecting_row_in_list_selects_matching_card_on_canvas(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)

    row = window.card_table_model.row_for_card_id("c_7bd310aa")
    window.list_view.table_view.selectRow(row)

    item = window.canvas_scene.item_for_card("c_7bd310aa")
    assert item.isSelected()
    other_item = window.canvas_scene.item_for_card("c_4f9a1b2c")
    assert not other_item.isSelected()
    assert "Card two" in window.card_table_model.index(row, COLUMN_TEXT).data()


def test_selection_survives_switching_views_back_and_forth(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)

    canvas_item = window.canvas_scene.item_for_card("c_1a2b3c4d")
    canvas_item.setSelected(True)

    row = window.card_table_model.row_for_card_id("c_7bd310aa")
    window.list_view.table_view.selectRow(row)

    assert window.canvas_scene.item_for_card("c_7bd310aa").isSelected()
    assert not window.canvas_scene.item_for_card("c_1a2b3c4d").isSelected()
    assert "Card two" in window.card_table_model.index(row, COLUMN_TEXT).data()


def test_holding_option_activates_link_mode_when_window_active(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    # isActiveWindow() reflects real OS/window-manager focus, which a
    # headless/automated test run can't reliably grant — force it so the
    # eventFilter's active-window gate takes the branch we're testing.
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)

    assert window.canvas_view.link_controller.active is False
    qtbot.keyPress(window, Qt.Key.Key_Alt)
    assert window.canvas_view.link_controller.active is True
    qtbot.keyRelease(window, Qt.Key.Key_Alt)
    assert window.canvas_view.link_controller.active is False


def test_holding_option_activates_link_mode_regardless_of_focused_widget(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    window.search_bar.line_edit.setFocus()

    qtbot.keyPress(window.search_bar.line_edit, Qt.Key.Key_Alt)

    assert window.canvas_view.link_controller.active is True


def test_option_key_ignored_when_window_not_active(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    press_event = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Alt, Qt.KeyboardModifier.NoModifier
    )
    window.eventFilter(window, press_event)

    assert window.canvas_view.link_controller.active is False


def test_option_key_autorepeat_is_ignored(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)

    repeat_event = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Alt, Qt.KeyboardModifier.NoModifier, autorep=True
    )
    window.eventFilter(window, repeat_event)

    assert window.canvas_view.link_controller.active is False


def test_window_deactivation_turns_off_link_mode(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.canvas_view.link_controller.set_active(True)

    window.changeEvent(QEvent(QEvent.Type.ActivationChange))

    assert window.canvas_view.link_controller.active is False


def test_link_requested_pushes_add_link_command_and_undo_works(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)

    window._on_link_requested("c_4f9a1b2c", "c_1a2b3c4d")

    new_links = [
        link
        for link in window.document.links.values()
        if link.source == "c_4f9a1b2c" and link.target == "c_1a2b3c4d"
    ]
    assert len(new_links) == 1
    assert window.undo_stack.canUndo()

    window.undo_stack.undo()
    assert not any(
        link.source == "c_4f9a1b2c" and link.target == "c_1a2b3c4d"
        for link in window.document.links.values()
    )


def test_canvas_delete_requested_removes_selected_link(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)

    link_item = next(
        item
        for item in window.canvas_scene.items()
        if isinstance(item, LinkItem) and item.link_id == "l_9e21ab04"
    )
    link_item.setSelected(True)

    window._on_canvas_delete_requested()

    assert "l_9e21ab04" not in window.document.links
    assert window.undo_stack.canUndo()

    window.undo_stack.undo()
    assert "l_9e21ab04" in window.document.links


def test_canvas_delete_card_asks_for_confirmation_and_cascades(qtbot, monkeypatch):
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.Yes)
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)

    # c_4f9a1b2c is one endpoint of the fixture's only link, l_9e21ab04.
    window.canvas_scene.item_for_card("c_4f9a1b2c").setSelected(True)

    window._on_canvas_delete_requested()

    assert "c_4f9a1b2c" not in window.document.cards
    assert "l_9e21ab04" not in window.document.links
    assert window.undo_stack.canUndo()

    window.undo_stack.undo()
    assert "c_4f9a1b2c" in window.document.cards
    assert "l_9e21ab04" in window.document.links


def test_canvas_delete_card_declined_confirmation_deletes_nothing(qtbot, monkeypatch):
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.No)
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)

    window.canvas_scene.item_for_card("c_4f9a1b2c").setSelected(True)

    window._on_canvas_delete_requested()

    assert "c_4f9a1b2c" in window.document.cards
    assert window.undo_stack.canUndo() is False


def test_canvas_delete_card_plus_its_own_incident_link_does_not_double_delete(qtbot, monkeypatch):
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.Yes)
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)

    # Select both the card AND its own incident link at once — selecting the
    # link is redundant with the cascade, and previously this combination
    # would crash (double-delete of the same link).
    window.canvas_scene.item_for_card("c_4f9a1b2c").setSelected(True)
    link_item = next(
        item
        for item in window.canvas_scene.items()
        if isinstance(item, LinkItem) and item.link_id == "l_9e21ab04"
    )
    link_item.setSelected(True)

    window._on_canvas_delete_requested()  # must not raise

    assert "c_4f9a1b2c" not in window.document.cards
    assert "l_9e21ab04" not in window.document.links

    window.undo_stack.undo()
    assert "c_4f9a1b2c" in window.document.cards
    assert "l_9e21ab04" in window.document.links


def test_list_delete_asks_for_confirmation(qtbot, monkeypatch):
    seen_messages = []

    def fake_exec(self):
        seen_messages.append(self.text())
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)

    row = window.card_table_model.row_for_card_id("c_4f9a1b2c")
    window.list_view.table_view.selectRow(row)
    window.list_view._delete_selected_cards()

    assert len(seen_messages) == 1
    assert "1 connected link" in seen_messages[0]
    assert "c_4f9a1b2c" not in window.document.cards
    assert "l_9e21ab04" not in window.document.links


def test_list_delete_declined_confirmation_deletes_nothing(qtbot, monkeypatch):
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.No)
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)

    row = window.card_table_model.row_for_card_id("c_4f9a1b2c")
    window.list_view.table_view.selectRow(row)
    window.list_view._delete_selected_cards()

    assert "c_4f9a1b2c" in window.document.cards


def test_search_filters_list_and_dims_canvas(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)

    window.search_bar.line_edit.setText("untagged")

    assert window.list_view.proxy_model.rowCount() == 1
    row = window.list_view.proxy_model.mapToSource(window.list_view.proxy_model.index(0, 0)).row()
    assert window.card_table_model.card_id_at_row(row) == "c_1a2b3c4d"

    assert window.canvas_scene.item_for_card("c_1a2b3c4d")._dimmed is False
    assert window.canvas_scene.item_for_card("c_4f9a1b2c")._dimmed is True
    assert window.canvas_scene.item_for_card("c_7bd310aa")._dimmed is True
    # l_9e21ab04 connects c_4f9a1b2c <-> c_7bd310aa, neither of which matches.
    link_item = next(
        item for item in window.canvas_scene.items() if isinstance(item, LinkItem)
    )
    assert link_item._dimmed is True


def test_clearing_search_restores_everything(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)

    window.search_bar.line_edit.setText("untagged")
    window.search_bar.line_edit.setText("")

    assert window.list_view.proxy_model.rowCount() == 3
    for card_id in ("c_4f9a1b2c", "c_7bd310aa", "c_1a2b3c4d"):
        assert window.canvas_scene.item_for_card(card_id)._dimmed is False
    link_item = next(
        item for item in window.canvas_scene.items() if isinstance(item, LinkItem)
    )
    assert link_item._dimmed is False


def test_search_query_survives_opening_a_new_document(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)
    window.search_bar.line_edit.setText("untagged")

    window.open_file(FIXTURE_PATH)

    assert window.list_view.proxy_model.rowCount() == 1


def test_main_window_has_theme_menu_between_view_and_arrange(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    menu_titles = [action.text() for action in window.menuBar().actions()]
    assert menu_titles.index("&Theme") == menu_titles.index("&View") + 1
    assert menu_titles.index("&Arrange") == menu_titles.index("&Theme") + 1


def test_arrange_menu_has_tile_scatter_and_columns_submenu(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    arrange_menu = next(
        action.menu() for action in window.menuBar().actions() if action.text() == "&Arrange"
    )
    action_texts = [action.text() for action in arrange_menu.actions()]
    assert action_texts == [
        "Align",
        "Distribute",
        "",
        "Tile",
        "Scatter",
        "Columns",
        "Tidy to Edges",
        "Sweep to Edges",
        "",
        "Gather Stacks",
        "Untangle Links",
    ]
    assert window.align_menu.menuAction() in arrange_menu.actions()
    assert window.distribute_menu.menuAction() in arrange_menu.actions()
    assert window.arrange_tile_action in arrange_menu.actions()
    assert window.arrange_scatter_action in arrange_menu.actions()
    assert window.arrange_columns_menu.menuAction() in arrange_menu.actions()
    assert window.untangle_links_action in arrange_menu.actions()
    assert window.gather_stacks_action in arrange_menu.actions()


def test_arrange_columns_submenu_has_by_color_and_alphabetical(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    action_texts = [action.text() for action in window.arrange_columns_menu.actions()]
    assert action_texts == ["By Color", "Alphabetical"]
    assert window.arrange_columns_by_color_action in window.arrange_columns_menu.actions()
    assert window.arrange_columns_alphabetical_action in window.arrange_columns_menu.actions()


def _arrange_actions(window: MainWindow) -> list[QAction]:
    return [
        window.arrange_tile_action,
        window.arrange_scatter_action,
        window.arrange_columns_by_color_action,
        window.arrange_columns_alphabetical_action,
    ]


def test_arrange_actions_disabled_with_no_cards(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window._update_arrange_actions_enabled()

    assert not any(action.isEnabled() for action in _arrange_actions(window))
    assert not window.arrange_columns_menu.menuAction().isEnabled()


def test_arrange_actions_disabled_with_only_one_card(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Arrange Test")
    document.add_card(Card(id="c_1"))
    window._set_document(document, path=None)

    window._update_arrange_actions_enabled()

    assert not any(action.isEnabled() for action in _arrange_actions(window))


def test_arrange_actions_enabled_with_two_or_more_cards(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Arrange Test")
    document.add_card(Card(id="c_1"))
    document.add_card(Card(id="c_2"))
    window._set_document(document, path=None)

    window._update_arrange_actions_enabled()

    assert all(action.isEnabled() for action in _arrange_actions(window))
    assert window.arrange_columns_menu.menuAction().isEnabled()


def test_arrange_actions_disabled_with_all_cards_pinned(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Arrange Test")
    document.add_card(Card(id="c_1", pinned=True))
    document.add_card(Card(id="c_2", pinned=True))
    window._set_document(document, path=None)

    window._update_arrange_actions_enabled()

    assert not any(action.isEnabled() for action in _arrange_actions(window))


def test_arrange_actions_disabled_with_only_one_unpinned_card(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Arrange Test")
    document.add_card(Card(id="c_1", pinned=True))
    document.add_card(Card(id="c_2", pinned=False))
    window._set_document(document, path=None)

    window._update_arrange_actions_enabled()

    assert not any(action.isEnabled() for action in _arrange_actions(window))


def test_arrange_actions_enabled_with_two_unpinned_cards_among_pinned_ones(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Arrange Test")
    document.add_card(Card(id="c_1", pinned=True))
    document.add_card(Card(id="c_2", pinned=False))
    document.add_card(Card(id="c_3", pinned=False))
    window._set_document(document, path=None)

    window._update_arrange_actions_enabled()

    assert all(action.isEnabled() for action in _arrange_actions(window))


def test_align_distribute_actions_disabled_with_fewer_than_two_selected_cards(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Arrange Test")
    document.add_card(Card(id="c_1"))
    document.add_card(Card(id="c_2"))
    window._set_document(document, path=None)

    window._update_arrange_actions_enabled()

    assert not window.align_horizontal_action.isEnabled()
    assert not window.align_vertical_action.isEnabled()
    assert not window.distribute_horizontal_action.isEnabled()
    assert not window.distribute_vertical_action.isEnabled()
    assert not window.align_menu.menuAction().isEnabled()
    assert not window.distribute_menu.menuAction().isEnabled()

    window.canvas_scene.item_for_card("c_1").setSelected(True)
    window._update_arrange_actions_enabled()

    assert not window.align_horizontal_action.isEnabled()


def test_align_distribute_actions_enabled_with_two_or_more_selected_cards(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Arrange Test")
    document.add_card(Card(id="c_1"))
    document.add_card(Card(id="c_2"))
    window._set_document(document, path=None)

    window.canvas_scene.item_for_card("c_1").setSelected(True)
    window.canvas_scene.item_for_card("c_2").setSelected(True)
    window._update_arrange_actions_enabled()

    assert window.align_horizontal_action.isEnabled()
    assert window.align_vertical_action.isEnabled()
    assert window.distribute_horizontal_action.isEnabled()
    assert window.distribute_vertical_action.isEnabled()
    assert window.align_menu.menuAction().isEnabled()
    assert window.distribute_menu.menuAction().isEnabled()


def test_align_horizontal_action_aligns_the_selected_cards(qtbot):
    # "Horizontally" names the axis of movement (matching Distribute's
    # own convention) -- moving cards horizontally lines them up onto a
    # shared vertical line, i.e. the same x.
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Arrange Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    document.add_card(Card(id="c_2", x=300.0, y=200.0))
    window._set_document(document, path=None)

    window.canvas_scene.item_for_card("c_1").setSelected(True)
    window.canvas_scene.item_for_card("c_2").setSelected(True)
    window._update_arrange_actions_enabled()
    window.align_horizontal_action.trigger()

    assert window.undo_stack.canUndo()
    assert document.get_card("c_1").x == document.get_card("c_2").x
    assert document.get_card("c_1").y == 0.0
    assert document.get_card("c_2").y == 200.0


def test_align_vertical_action_aligns_the_selected_cards(qtbot):
    # Moving cards vertically lines them up onto a shared horizontal
    # line, i.e. the same y.
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Arrange Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    document.add_card(Card(id="c_2", x=200.0, y=300.0))
    window._set_document(document, path=None)

    window.canvas_scene.item_for_card("c_1").setSelected(True)
    window.canvas_scene.item_for_card("c_2").setSelected(True)
    window._update_arrange_actions_enabled()
    window.align_vertical_action.trigger()

    assert window.undo_stack.canUndo()
    assert document.get_card("c_1").y == document.get_card("c_2").y
    assert document.get_card("c_1").x == 0.0
    assert document.get_card("c_2").x == 200.0


def test_distribute_horizontal_action_spaces_the_selected_cards_evenly(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Arrange Test")
    document.add_card(Card(id="c_0", x=0.0, y=0.0))
    document.add_card(Card(id="c_1", x=10.0, y=50.0))
    document.add_card(Card(id="c_2", x=900.0, y=100.0))
    window._set_document(document, path=None)
    for card_id in ("c_0", "c_1", "c_2"):
        window.canvas_scene.item_for_card(card_id).setSelected(True)

    window._update_arrange_actions_enabled()
    window.distribute_horizontal_action.trigger()

    assert window.undo_stack.canUndo()
    assert document.get_card("c_0").x == 0.0
    assert document.get_card("c_2").x == 900.0
    assert document.get_card("c_1").x == 450.0
    # y untouched
    assert document.get_card("c_1").y == 50.0


def test_distribute_vertical_action_spaces_the_selected_cards_evenly(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Arrange Test")
    document.add_card(Card(id="c_0", x=0.0, y=0.0))
    document.add_card(Card(id="c_1", x=50.0, y=10.0))
    document.add_card(Card(id="c_2", x=100.0, y=900.0))
    window._set_document(document, path=None)
    for card_id in ("c_0", "c_1", "c_2"):
        window.canvas_scene.item_for_card(card_id).setSelected(True)

    window._update_arrange_actions_enabled()
    window.distribute_vertical_action.trigger()

    assert window.undo_stack.canUndo()
    assert document.get_card("c_0").y == 0.0
    assert document.get_card("c_2").y == 900.0
    assert document.get_card("c_1").y == 450.0
    # x untouched
    assert document.get_card("c_1").x == 50.0


def test_run_align_does_nothing_with_fewer_than_two_selected_cards(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Arrange Test")
    document.add_card(Card(id="c_1"))
    window._set_document(document, path=None)

    window.canvas_scene.item_for_card("c_1").setSelected(True)
    window._run_align("horizontal")

    assert not window.undo_stack.canUndo()


def test_untangle_links_action_disabled_without_any_links(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Arrange Test")
    document.add_card(Card(id="c_1"))
    document.add_card(Card(id="c_2"))
    window._set_document(document, path=None)

    window._update_arrange_actions_enabled()

    assert not window.untangle_links_action.isEnabled()


def test_untangle_links_action_enabled_with_a_link_between_eligible_cards(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Arrange Test")
    document.add_card(Card(id="c_1"))
    document.add_card(Card(id="c_2"))
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    window._set_document(document, path=None)

    window._update_arrange_actions_enabled()

    assert window.untangle_links_action.isEnabled()


def test_untangle_links_action_enabled_when_the_only_link_is_between_pinned_cards(qtbot):
    # Untangle Links deliberately ignores pinned status -- unlike every
    # other Arrange action, a link between two pinned cards is still a
    # real graph it can untangle.
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Arrange Test")
    document.add_card(Card(id="c_1", pinned=True))
    document.add_card(Card(id="c_2", pinned=True))
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    window._set_document(document, path=None)

    window._update_arrange_actions_enabled()

    assert window.untangle_links_action.isEnabled()


def test_untangle_links_action_pushes_an_auto_arrange_command(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Arrange Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    document.add_card(Card(id="c_2", x=0.0, y=0.0))
    document.add_card(Card(id="c_3", x=500.0, y=500.0))
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    window._set_document(document, path=None)

    window.untangle_links_action.trigger()

    assert window.undo_stack.canUndo()
    assert document.get_card("c_1").x != document.get_card("c_2").x or (
        document.get_card("c_1").y != document.get_card("c_2").y
    )


def test_untangle_links_moves_pinned_cards_too(qtbot):
    # Unlike every other Arrange action, Untangle Links deliberately
    # ignores pinned status -- both from the whole-document fallback...
    # Checked by no-longer-overlapping rather than "moved off (0, 0)":
    # the whole-document mode packs its result anchored at the origin,
    # so with the deterministic layout it's possible (and fine) for
    # whichever card ends up at the packed cluster's own top-left corner
    # to legitimately land back on (0, 0) by coincidence.
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Arrange Test")
    document.add_card(Card(id="c_1", pinned=True, x=0.0, y=0.0))
    document.add_card(Card(id="c_2", x=0.0, y=0.0))
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    window._set_document(document, path=None)

    window.untangle_links_action.trigger()

    assert window.undo_stack.canUndo()
    c1 = document.get_card("c_1")
    c2 = document.get_card("c_2")
    assert (c1.x, c1.y) != (c2.x, c2.y)


def test_untangle_links_with_a_selection_moves_pinned_cards_too(qtbot):
    # ...and from the selection-scoped path.
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Arrange Test")
    document.add_card(Card(id="c_1", pinned=True, x=0.0, y=0.0))
    document.add_card(Card(id="c_2", x=0.0, y=0.0))
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    window._set_document(document, path=None)

    window.canvas_scene.item_for_card("c_1").setSelected(True)
    window._run_untangle_links()

    assert window.undo_stack.canUndo()
    assert (document.get_card("c_1").x, document.get_card("c_1").y) != (0.0, 0.0)


def test_untangle_links_with_a_selection_only_touches_the_selected_graph(qtbot):
    # Two separate link chains plus an isolated card -- selecting a card
    # in ONE chain should untangle just that chain, leaving the other
    # chain and the isolated card exactly where they started.
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Arrange Test")
    document.add_card(Card(id="a1", x=0.0, y=0.0))
    document.add_card(Card(id="a2", x=0.0, y=0.0))
    document.add_link(Link(id="l_a", source="a1", target="a2"))
    document.add_card(Card(id="b1", x=1000.0, y=1000.0))
    document.add_card(Card(id="b2", x=1000.0, y=1000.0))
    document.add_link(Link(id="l_b", source="b1", target="b2"))
    document.add_card(Card(id="iso", x=2000.0, y=2000.0))
    window._set_document(document, path=None)

    window.canvas_scene.item_for_card("a1").setSelected(True)
    window._run_untangle_links()

    assert window.undo_stack.canUndo()
    assert (document.get_card("b1").x, document.get_card("b1").y) == (1000.0, 1000.0)
    assert (document.get_card("b2").x, document.get_card("b2").y) == (1000.0, 1000.0)
    assert (document.get_card("iso").x, document.get_card("iso").y) == (2000.0, 2000.0)


def test_untangle_links_with_an_unlinked_selection_falls_back_to_whole_document(qtbot):
    # Selecting a card with no links at all should behave exactly like
    # having no selection: untangle every real graph in the document.
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Arrange Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    document.add_card(Card(id="c_2", x=0.0, y=0.0))
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    document.add_card(Card(id="iso", x=500.0, y=500.0))
    window._set_document(document, path=None)

    window.canvas_scene.item_for_card("iso").setSelected(True)
    window._run_untangle_links()

    assert window.undo_stack.canUndo()
    assert document.get_card("c_1").x != document.get_card("c_2").x or (
        document.get_card("c_1").y != document.get_card("c_2").y
    )


def test_auto_arrange_columns_by_color_groups_and_undo_restores_layout(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Arrange Test")
    document.add_card(Card(id="c_1", color_slot="slot_blue", x=1.0, y=2.0))
    document.add_card(Card(id="c_2", color_slot="slot_blue", x=3.0, y=4.0))
    document.add_card(Card(id="c_3", color_slot="slot_green", x=5.0, y=6.0))
    window._set_document(document, path=None)
    original_positions = {card.id: (card.x, card.y) for card in document.iter_cards()}

    window.arrange_columns_by_color_action.trigger()

    # c_1 and c_2 share a color, so they land in the same column (same x);
    # c_3 is a different color and lands in a different column.
    assert document.get_card("c_1").x == document.get_card("c_2").x
    assert document.get_card("c_3").x != document.get_card("c_1").x
    assert window.undo_stack.canUndo()

    window.undo_stack.undo()
    for card_id, pos in original_positions.items():
        assert (document.get_card(card_id).x, document.get_card(card_id).y) == pos


def test_auto_arrange_columns_alphabetical_groups_by_first_letter(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Arrange Test")
    document.add_card(Card(id="c_1", text="Apple"))
    document.add_card(Card(id="c_2", text="Avocado"))
    document.add_card(Card(id="c_3", text="Banana"))
    window._set_document(document, path=None)

    window.arrange_columns_alphabetical_action.trigger()

    assert document.get_card("c_1").x == document.get_card("c_2").x
    assert document.get_card("c_3").x != document.get_card("c_1").x
    assert window.undo_stack.canUndo()


def test_auto_arrange_tile_mode_lays_out_a_grid(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(1000, 700)
    document = Document(name="Arrange Test")
    for i in range(6):
        document.add_card(Card(id=f"c_{i}", x=float(i), y=float(i)))
    window._set_document(document, path=None)

    window.arrange_tile_action.trigger()

    positions = {(c.x, c.y) for c in document.iter_cards()}
    assert len(positions) == 6  # no two cards landed on the same spot
    assert window.undo_stack.canUndo()


def test_auto_arrange_scatter_mode_places_first_card_at_origin(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(1000, 700)
    document = Document(name="Arrange Test")
    for i in range(6):
        document.add_card(Card(id=f"c_{i}", x=float(i), y=float(i)))
    window._set_document(document, path=None)

    window.arrange_scatter_action.trigger()

    first_card = next(document.iter_cards())
    assert (first_card.x, first_card.y) == (0.0, 0.0)
    assert window.undo_stack.canUndo()


def test_auto_arrange_all_pinned_does_nothing(qtbot):
    # Calls _run_auto_arrange directly (bypassing the action's own enabled
    # gate, which now also disables for this case) so this still exercises
    # _run_auto_arrange's own guard clause as defense-in-depth.
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Arrange Test")
    document.add_card(Card(id="c_1", x=1.0, y=2.0, pinned=True))
    window._set_document(document, path=None)

    window._run_auto_arrange("color")

    assert window.undo_stack.canUndo() is False
    assert (document.get_card("c_1").x, document.get_card("c_1").y) == (1.0, 2.0)


def test_auto_arrange_passes_viewport_aspect_ratio(qtbot, monkeypatch):
    captured = {}

    def fake_arrange_avoiding_obstacles(
        cards,
        group_by,
        tag=None,
        aspect_ratio=1.0,
        overflow_limit=None,
        theme=None,
        stack_positions=None,
    ):
        captured["aspect_ratio"] = aspect_ratio
        return {card.id: (card.x, card.y) for card in cards}

    monkeypatch.setattr(
        "indexcards.main_window.arrange_avoiding_obstacles", fake_arrange_avoiding_obstacles
    )

    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(1000, 700)
    window.show()
    qtbot.waitActive(window)
    document = Document(name="Arrange Test")
    document.add_card(Card(id="c_1"))
    document.add_card(Card(id="c_2"))
    window._set_document(document, path=None)

    window.arrange_columns_by_color_action.trigger()

    viewport = window.canvas_view.viewport().size()
    expected = viewport.width() / viewport.height()
    assert captured["aspect_ratio"] == pytest.approx(expected)


def test_auto_arrange_does_not_zoom_when_cards_still_fit(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(1000, 700)
    window.show()
    qtbot.waitActive(window)
    document = Document(name="Arrange Test")
    document.add_card(Card(id="c_1", color_slot="slot_blue", x=1.0, y=2.0))
    document.add_card(Card(id="c_2", color_slot="slot_blue", x=3.0, y=4.0))
    document.add_card(Card(id="c_3", color_slot="slot_green", x=5.0, y=6.0))
    window._set_document(document, path=None)
    zoom_before = window.canvas_view.zoom

    window.arrange_columns_by_color_action.trigger()

    assert window.canvas_view.zoom == zoom_before


def test_auto_arrange_zooms_out_when_new_layout_does_not_fit(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(400, 300)
    window.show()
    qtbot.waitActive(window)
    document = Document(name="Arrange Test")
    slots = [
        "slot_white",
        "slot_yellow",
        "slot_blue",
        "slot_green",
        "slot_pink",
        "slot_purple",
    ]
    for i, slot_id in enumerate(slots):
        document.add_card(Card(id=f"c_{i}", color_slot=slot_id, x=float(i), y=float(i)))
    window._set_document(document, path=None)
    zoom_before = window.canvas_view.zoom

    window.arrange_columns_by_color_action.trigger()

    assert window.canvas_view.zoom < zoom_before


def test_auto_arrange_pans_without_zooming_when_content_fits_but_scrolled_away(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(1000, 700)
    window.show()
    qtbot.waitActive(window)
    document = Document(name="Arrange Test")
    document.add_card(Card(id="c_1", color_slot="slot_blue", x=1.0, y=2.0))
    document.add_card(Card(id="c_2", color_slot="slot_blue", x=3.0, y=4.0))
    document.add_card(Card(id="c_3", color_slot="slot_green", x=5.0, y=6.0))
    window._set_document(document, path=None)
    window.canvas_scene.setSceneRect(-10000.0, -10000.0, 20000.0, 20000.0)
    window.canvas_view.centerOn(5000.0, 5000.0)
    zoom_before = window.canvas_view.zoom

    window.arrange_columns_by_color_action.trigger()

    assert window.canvas_view.zoom == zoom_before
    visible_rect = window.canvas_view.mapToScene(
        window.canvas_view.viewport().rect()
    ).boundingRect()
    assert visible_rect.contains(window.canvas_scene.itemsBoundingRect())


def test_auto_arrange_save_reload_preserves_new_layout(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)

    window.arrange_columns_by_color_action.trigger()
    new_positions = {card.id: (card.x, card.y) for card in window.document.iter_cards()}

    save_path = tmp_path / "arranged.idxcards"
    window._save_to(save_path)

    reloaded = load_document(save_path)
    for card_id, pos in new_positions.items():
        card = reloaded.get_card(card_id)
        assert (card.x, card.y) == pos


def test_close_event_with_clean_document_accepts_immediately(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    event = QCloseEvent()
    window.closeEvent(event)

    assert event.isAccepted()


def test_close_event_with_unsaved_changes_cancel_ignores_close(qtbot, monkeypatch):
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Cancel)
    )
    window = MainWindow()
    qtbot.addWidget(window)
    window.card_table_model.add_card()
    assert window.undo_stack.isClean() is False

    event = QCloseEvent()
    window.closeEvent(event)

    assert event.isAccepted() is False


def test_close_event_with_unsaved_changes_discard_accepts_close(qtbot, monkeypatch):
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Discard)
    )
    window = MainWindow()
    qtbot.addWidget(window)
    window.card_table_model.add_card()

    event = QCloseEvent()
    window.closeEvent(event)

    assert event.isAccepted() is True


def test_close_event_with_unsaved_changes_save_succeeds_and_accepts(qtbot, monkeypatch, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.card_table_model.add_card()
    save_path = tmp_path / "test.idxcards"
    window._save_to(save_path)
    assert window.undo_stack.isClean()

    window.card_table_model.add_card()
    assert window.undo_stack.isClean() is False

    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Save)
    )
    event = QCloseEvent()
    window.closeEvent(event)

    assert event.isAccepted() is True
    assert window.undo_stack.isClean() is True


def test_close_event_save_with_cancelled_save_as_ignores_close(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    window.card_table_model.add_card()  # dirty, and no path yet

    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Save)
    )
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", ""))
    )

    event = QCloseEvent()
    window.closeEvent(event)

    assert event.isAccepted() is False


def test_close_event_notifies_window_manager(qtbot):
    manager = WindowManager()
    window = manager.open_new_window()
    qtbot.addWidget(window)
    assert window in manager._windows

    event = QCloseEvent()
    window.closeEvent(event)

    assert window not in manager._windows


def test_new_window_action_delegates_to_window_manager(qtbot):
    manager = WindowManager()
    window = manager.open_new_window()
    qtbot.addWidget(window)

    window._on_new()

    assert len(manager._windows) == 2


def test_open_action_on_blank_window_reuses_it_instead_of_opening_new(qtbot, monkeypatch):
    manager = WindowManager()
    window = manager.open_new_window()
    qtbot.addWidget(window)
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        staticmethod(lambda *a, **k: (str(FIXTURE_PATH), "")),
    )

    window._on_open()

    assert len(manager._windows) == 1
    assert window.document.name == "sample"
    assert window.current_path == FIXTURE_PATH


def test_open_action_on_non_reusable_window_opens_a_new_window(qtbot, monkeypatch, tmp_path):
    other_path = tmp_path / "other.idxcards"
    document = Document(name="Other")
    document.add_card(Card(id="c_1"))
    save_document(document, other_path)

    manager = WindowManager()
    window = manager.open_file(other_path)  # not reusable: has a path
    qtbot.addWidget(window)
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        staticmethod(lambda *a, **k: (str(FIXTURE_PATH), "")),
    )

    window._on_open()

    assert len(manager._windows) == 2
    new_window = next(w for w in manager._windows if w is not window)
    assert new_window.document.name == "sample"
    assert window.document.name == "other"  # original window untouched


def test_is_reusable_false_after_edit(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.is_reusable() is True

    window.card_table_model.add_card()

    assert window.is_reusable() is False


def test_is_reusable_false_once_a_path_is_set(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window.open_file(FIXTURE_PATH)

    assert window.is_reusable() is False


def test_open_action_reopening_same_file_focuses_existing_window(qtbot, monkeypatch):
    manager = WindowManager()
    window = manager.open_file(FIXTURE_PATH)
    qtbot.addWidget(window)
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        staticmethod(lambda *a, **k: (str(FIXTURE_PATH), "")),
    )

    window._on_open()

    assert len(manager._windows) == 1


def test_activate_undo_stack_retargets_undo_group_so_undo_hits_focused_window(qtbot):
    manager = WindowManager()
    window1 = manager.open_new_window()
    window2 = manager.open_new_window()
    qtbot.addWidget(window1)
    qtbot.addWidget(window2)

    window1._activate_undo_stack()
    assert manager.undo_group.activeStack() is window1.undo_stack

    window2._activate_undo_stack()
    assert manager.undo_group.activeStack() is window2.undo_stack

    window2.card_table_model.add_card()
    assert window1.card_table_model.rowCount() == 0
    assert window2.card_table_model.rowCount() == 1

    manager.undo_group.undo()
    assert window2.card_table_model.rowCount() == 0


def test_focus_search_bar_gives_search_field_focus_and_selection(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitActive(window)
    window.search_bar.line_edit.setText("existing query")

    window._focus_search_bar()

    qtbot.waitUntil(lambda: window.search_bar.line_edit.hasFocus())
    assert window.search_bar.line_edit.selectedText() == "existing query"


def test_main_window_has_no_canvas_toolbar(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert not hasattr(window, "canvas_toolbar")


def test_view_menu_has_canvas_background_action(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    view_menu = next(
        action.menu() for action in window.menuBar().actions() if action.text() == "&View"
    )
    assert window.canvas_background_action in view_menu.actions()
    assert window.canvas_background_action.text() == "Canvas Background"


def test_canvas_background_action_triggers_change_background(qtbot, monkeypatch):
    monkeypatch.setattr(
        QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor("#123456"))
    )
    window = MainWindow()
    qtbot.addWidget(window)

    window.canvas_background_action.trigger()

    assert window.document.canvas_background_color == "#123456"


def test_canvas_view_background_change_requested_triggers_change_background(qtbot, monkeypatch):
    monkeypatch.setattr(
        QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor("#654321"))
    )
    window = MainWindow()
    qtbot.addWidget(window)

    window.canvas_view.backgroundChangeRequested.emit()

    assert window.document.canvas_background_color == "#654321"


def test_change_canvas_background_pushes_command(qtbot, monkeypatch):
    monkeypatch.setattr(
        QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor("#123456"))
    )
    window = MainWindow()
    qtbot.addWidget(window)

    window._on_change_canvas_background()

    assert window.document.canvas_background_color == "#123456"
    assert window.undo_stack.canUndo()

    window.undo_stack.undo()
    assert window.document.canvas_background_color != "#123456"


def test_change_canvas_background_cancelled_dialog_does_nothing(qtbot, monkeypatch):
    monkeypatch.setattr(QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor()))
    window = MainWindow()
    qtbot.addWidget(window)
    original_color = window.document.canvas_background_color

    window._on_change_canvas_background()

    assert window.document.canvas_background_color == original_color
    assert window.undo_stack.canUndo() is False


def test_change_canvas_background_same_color_does_not_push_command(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    current_color = window.document.canvas_background_color
    monkeypatch.setattr(
        QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor(current_color))
    )

    window._on_change_canvas_background()

    assert window.undo_stack.canUndo() is False


def test_settings_action_has_preferences_shortcut_and_role(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.settings_action.shortcut() == QKeySequence(QKeySequence.StandardKey.Preferences)
    assert window.settings_action.menuRole() == QAction.MenuRole.PreferencesRole


def test_open_settings_accepted_updates_shared_settings(qtbot, monkeypatch):
    def fake_exec(self):
        self.warn_before_delete_checkbox.setChecked(False)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(SettingsDialog, "exec", fake_exec)
    window = MainWindow()
    qtbot.addWidget(window)

    window._on_open_settings()

    assert window._settings.warn_before_delete is False


def test_open_settings_cancelled_leaves_settings_unchanged(qtbot, monkeypatch):
    monkeypatch.setattr(SettingsDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    window = MainWindow()
    qtbot.addWidget(window)

    window._on_open_settings()

    assert window._settings.warn_before_delete is True


def test_edit_current_theme_opens_settings_dialog_on_themes_pane(qtbot, monkeypatch):
    seen = {}

    def fake_exec(self):
        seen["initial_pane"] = self._stack.currentWidget() is self._themes_pane
        seen["preselected_id"] = self.themes_pane._current_theme_id
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(SettingsDialog, "exec", fake_exec)
    window = MainWindow()
    qtbot.addWidget(window)

    window._on_edit_current_theme()

    assert seen["initial_pane"] is True
    assert seen["preselected_id"] == window.document.theme.id


def test_edit_current_theme_accepted_pushes_undoable_theme_change(qtbot, monkeypatch):
    def fake_exec(self):
        self.themes_pane.editor._row_widget(0).label_edit.setText("Renamed")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(SettingsDialog, "exec", fake_exec)
    window = MainWindow()
    qtbot.addWidget(window)
    old_theme = window.document.theme

    window._on_edit_current_theme()

    assert window.document.theme is not old_theme
    assert window.document.theme.slots[0].label == "Renamed"
    assert window.undo_stack.canUndo()

    window.undo_stack.undo()
    assert window.document.theme is old_theme


def test_edit_current_theme_cancelled_leaves_theme_unchanged(qtbot, monkeypatch):
    monkeypatch.setattr(SettingsDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    window = MainWindow()
    qtbot.addWidget(window)
    old_theme = window.document.theme

    window._on_edit_current_theme()

    assert window.document.theme is old_theme
    assert window.undo_stack.canUndo() is False


def test_edit_current_theme_warns_when_removing_an_in_use_slot(qtbot, monkeypatch):
    theme = Theme(
        id="t_1",
        name="Test",
        origin="custom",
        background_color="#000000",
        slots=[Slot(id="slot_only", label="Only", hex="#ff0000")],
    )
    window = MainWindow()
    qtbot.addWidget(window)
    window.document.set_theme_snapshot(theme)
    window.card_table_model.add_card()  # seeds color_slot="slot_only" (theme's only slot)

    def fake_exec(self):
        self.themes_pane.editor.slot_list.takeItem(0)  # remove the theme's only (in-use) slot
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(SettingsDialog, "exec", fake_exec)
    monkeypatch.setattr(OrphanResolutionDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    warnings = []
    monkeypatch.setattr(
        QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a))
    )

    window._on_edit_current_theme()

    assert warnings  # the warning dialog was shown
    assert window.document.get_slot("slot_only").orphaned is True


def test_edit_current_theme_deleted_falls_back_to_classic(qtbot, monkeypatch):
    theme = Theme(
        id="t_1", name="Test", origin="custom", background_color="#000000",
        slots=[Slot(id="slot_only", label="Only", hex="#ff0000")],
    )
    window = MainWindow()
    qtbot.addWidget(window)
    window.document.set_theme_snapshot(theme)
    window._theme_library.add(theme)

    def fake_exec(self):
        self.themes_pane.remove_button.click()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(SettingsDialog, "exec", fake_exec)

    window._on_edit_current_theme()

    assert window.document.theme.id == "preset_classic"
    assert window.undo_stack.canUndo()


def test_select_theme_pushes_undoable_theme_change(qtbot):
    target = Theme(
        id="custom_target", name="Target", origin="custom", background_color="#000000",
        slots=[Slot(id="slot_x", label="X", hex="#eeeeee")],
    )
    window = MainWindow()
    qtbot.addWidget(window)
    old_theme = window.document.theme

    window._on_select_theme(target)

    assert window.document.theme is not old_theme
    assert window.document.theme.id == "custom_target"
    assert window.undo_stack.canUndo()

    window.undo_stack.undo()
    assert window.document.theme is old_theme


def test_select_theme_updates_canvas_background(qtbot):
    target = Theme(
        id="custom_target", name="Target", origin="custom", background_color="#654321",
        slots=[Slot(id="slot_x", label="X", hex="#eeeeee")],
    )
    window = MainWindow()
    qtbot.addWidget(window)
    original_background = window.canvas_scene.backgroundBrush().color().name()
    assert original_background != "#654321"

    window._on_select_theme(target)

    assert window.canvas_scene.backgroundBrush().color().name() == "#654321"

    window.undo_stack.undo()

    assert window.canvas_scene.backgroundBrush().color().name() == original_background


def test_select_theme_already_current_is_a_noop(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    current = window.document.theme

    window._on_select_theme(current)

    assert window.document.theme is current
    assert window.undo_stack.canUndo() is False


def test_select_theme_warns_when_switch_orphans_a_used_color(qtbot, monkeypatch):
    # No slots at all in the target — positional continuity (see
    # test_document_theme.py) has nowhere to put the used color, so this
    # is a genuine orphan regardless of how many colors the old theme had.
    target = Theme(
        id="custom_target", name="Target", origin="custom", background_color="#000000", slots=[]
    )
    monkeypatch.setattr(OrphanResolutionDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    window = MainWindow()
    qtbot.addWidget(window)
    window.card_table_model.add_card()  # uses the current theme's first slot

    warnings = []
    monkeypatch.setattr(
        QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a))
    )

    window._on_select_theme(target)

    assert warnings


def test_select_theme_between_same_size_presets_produces_no_orphans(qtbot, monkeypatch):
    # Regression for a real reported bug: switching between two 7-slot
    # presets (Classic -> Vivid) orphaned every card, because their slot
    # ids share nothing with each other. Positional continuity (see
    # test_document_theme.py) should carry every card across instead.
    vivid = get_preset_theme("preset_vivid")
    window = MainWindow()
    qtbot.addWidget(window)
    for slot in window.document.theme.slots:
        card_id = window.card_table_model.add_card()
        window.document.set_card_color_slot(card_id, slot.id)

    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a)))

    window._on_select_theme(vivid)

    assert warnings == []
    assert window.document.theme.id == "preset_vivid"
    assert all(not slot.orphaned for slot in window.document.theme.slots)
    assert {card.color_slot for card in window.document.cards.values()} == {
        slot.id for slot in vivid.slots
    }


def test_theme_menu_lists_presets_then_custom_themes(qtbot, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("My Copy", True)))
    window = MainWindow()
    qtbot.addWidget(window)
    window._on_duplicate_current_theme()

    window._rebuild_theme_list_section()

    labels = [action.text() for action in window._theme_list_actions]
    assert labels == [*[theme.name for theme in PRESET_THEMES], "My Copy"]


def test_theme_menu_checks_the_current_theme(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window._rebuild_theme_list_section()

    checked = [a for a in window._theme_list_actions if a.isChecked()]
    assert len(checked) == 1
    assert checked[0].text() == window.document.theme.name


def test_theme_menu_selecting_an_entry_switches_the_document(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window._rebuild_theme_list_section()
    other = next(
        a for a in window._theme_list_actions if a.text() != window.document.theme.name
    )

    other.trigger()

    assert window.document.theme.name == other.text()


def test_theme_menu_layout_matches_the_spec(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window._rebuild_theme_list_section()

    actions = window._theme_menu.actions()
    theme_count = len(window._theme_list_actions)
    assert actions[:theme_count] == window._theme_list_actions
    rest = [a.text() for a in actions[theme_count:]]
    assert rest == [
        "",
        "Edit Current Theme…",
        "Duplicate Current Theme…",
        "",
        "Resolve Orphaned Colors…",
    ]


def test_duplicate_current_theme_adds_to_library(qtbot, monkeypatch):
    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *a, **k: ("My Copy", True))
    )
    window = MainWindow()
    qtbot.addWidget(window)

    window._on_duplicate_current_theme()

    themes = window._theme_library.all()
    assert len(themes) == 1
    assert themes[0].name == "My Copy"
    assert themes[0].origin == "custom"


def test_duplicate_current_theme_cancelled_adds_nothing(qtbot, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("", False)))
    window = MainWindow()
    qtbot.addWidget(window)

    window._on_duplicate_current_theme()

    assert window._theme_library.all() == []


def test_new_document_uses_settings_default_theme(qtbot):
    manager = WindowManager(settings=AppSettings())
    custom_theme = Theme(id="custom_1", name="Mine", origin="custom", background_color="#abcdef")
    manager.theme_library.add(custom_theme)
    manager.settings.default_theme_id = "custom_1"

    window = manager.open_new_window()
    qtbot.addWidget(window)

    assert window.document.theme.id == "custom_1"
    assert window.document.canvas_background_color == "#abcdef"


def test_delete_skips_confirmation_when_warn_before_delete_disabled(qtbot, monkeypatch):
    def fail_if_called(self):
        raise AssertionError("QMessageBox.exec should not be called")

    monkeypatch.setattr(QMessageBox, "exec", fail_if_called)
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)
    window._settings.warn_before_delete = False

    window.canvas_scene.item_for_card("c_4f9a1b2c").setSelected(True)
    window._on_canvas_delete_requested()

    assert "c_4f9a1b2c" not in window.document.cards


def test_create_card_shortcut_on_canvas_tab_enters_edit_mode(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitActive(window)
    assert window.view_stack.currentWidget() is window.canvas_view

    window._on_create_card_shortcut()

    assert window.card_table_model.rowCount() == 1
    card_id = window.card_table_model.card_id_at_row(0)
    item = window.canvas_scene.item_for_card(card_id)
    qtbot.waitUntil(lambda: item._editing)


def test_create_card_shortcut_with_stack_overlay_open_adds_to_the_stack(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window._set_document(_document_with_stack(), path=None)
    window.canvas_view.resize(800, 600)
    window.canvas_view.stack_overlay.open("s_1", window.document, window.undo_stack)

    window._on_create_card_shortcut()

    assert window.canvas_view.stack_overlay.is_open is True
    assert len(window.document.get_stack("s_1").card_ids) == 3
    assert window.card_table_model.rowCount() == 3
    # Never visits the loose canvas -- CanvasScene skips a CardItem for
    # any card whose stack_id is set (canvas_scene.py's _add_item_for_card).
    new_card_id = [
        cid for cid in window.document.get_stack("s_1").card_ids if cid not in ("c_1", "c_2")
    ][0]
    assert window.canvas_scene.item_for_card(new_card_id) is None


def test_open_file_with_no_repairs_needed_shows_no_warning_dialog(qtbot, monkeypatch):
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a)))
    window = MainWindow()
    qtbot.addWidget(window)

    window.open_file(FIXTURE_PATH)

    assert warnings == []


def test_open_file_needing_repair_shows_a_warning_dialog(qtbot, monkeypatch, tmp_path):
    document = Document(name="Needs Repair")
    document.add_card(Card(id="c_1"))
    path = tmp_path / "needs_repair.idxcards"
    save_document(document, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["links"] = [{"id": "l_1", "source": "c_1", "target": "c_missing"}]
    path.write_text(json.dumps(data), encoding="utf-8")

    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a)))
    window = MainWindow()
    qtbot.addWidget(window)

    window.open_file(path)

    assert len(warnings) == 1
    assert "l_1" in warnings[0][-1]  # message text is the last positional arg
    assert "c_1" in window.document.cards
    assert "l_1" not in window.document.links


def test_list_view_card_created_edits_text_cell_on_list_tab(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitActive(window)
    window.view_stack.setCurrentWidget(window.list_view)

    window.list_view._add_card()

    assert window.card_table_model.rowCount() == 1
    assert window.list_view.table_view.state() == QAbstractItemView.State.EditingState
    assert window.list_view.table_view.currentIndex().row() == 0


def test_canvas_double_click_card_created_enters_edit_mode(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitActive(window)

    card_id = window.canvas_scene.add_card_at(100.0, 100.0)

    window._select_and_focus_new_card(card_id)

    item = window.canvas_scene.item_for_card(card_id)
    qtbot.waitUntil(lambda: item._editing)
    assert item.isSelected()


def test_select_and_focus_new_card_with_none_is_noop(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window._select_and_focus_new_card(None)  # must not raise


def test_main_window_has_view_menu_with_canvas_and_list_actions(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    menu_titles = [action.text() for action in window.menuBar().actions()]
    assert "&View" in menu_titles

    assert window.view_canvas_action.shortcut() == QKeySequence("Ctrl+1")
    assert window.view_list_action.shortcut() == QKeySequence("Ctrl+2")


def test_view_canvas_action_switches_to_canvas_tab(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.view_stack.setCurrentWidget(window.list_view)

    window.view_canvas_action.trigger()

    assert window.view_stack.currentWidget() is window.canvas_view


def test_view_list_action_switches_to_list_tab(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.view_stack.currentWidget() is window.canvas_view

    window.view_list_action.trigger()

    assert window.view_stack.currentWidget() is window.list_view


def test_switching_tabs_updates_view_menu_checked_state(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.view_canvas_action.isChecked()
    assert not window.view_list_action.isChecked()

    window.view_stack.setCurrentWidget(window.list_view)

    assert window.view_list_action.isChecked()
    assert not window.view_canvas_action.isChecked()


def test_select_all_on_canvas_tab_selects_all_cards(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)
    window.view_stack.setCurrentWidget(window.canvas_view)

    window._on_select_all()

    assert set(window.canvas_scene.selected_card_ids()) == set(window.document.cards.keys())


def test_select_all_on_list_tab_selects_all_rows(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)
    window.view_stack.setCurrentWidget(window.list_view)

    window._on_select_all()

    selected_rows = window.list_view.table_view.selectionModel().selectedRows()
    assert len(selected_rows) == len(window.document.cards)


def test_edit_menu_has_select_all_action(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    edit_menu = next(
        action.menu()
        for action in window.menuBar().actions()
        if action.text() == "&Edit"
    )
    action_texts = [action.text() for action in edit_menu.actions()]
    assert "Select &All" in action_texts


def test_view_menu_has_extents_action_with_shortcut(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.view_extents_action.shortcut() == QKeySequence("Ctrl+0")
    view_menu = next(
        action.menu() for action in window.menuBar().actions() if action.text() == "&View"
    )
    assert window.view_extents_action in view_menu.actions()


def test_view_extents_action_fits_all_cards_at_the_configured_margin(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    calls = []
    monkeypatch.setattr(
        window.canvas_view, "fit_to_content", lambda margin=None: calls.append(margin)
    )

    window.view_extents_action.trigger()

    assert calls == [VIEW_EXTENTS_MARGIN]


def test_view_menu_has_toggle_links_action_with_shortcut(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.toggle_links_action.shortcut() == QKeySequence("Ctrl+Shift+L")
    view_menu = next(
        action.menu() for action in window.menuBar().actions() if action.text() == "&View"
    )
    assert window.toggle_links_action in view_menu.actions()


def test_toggle_links_action_starts_as_hide_links(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.toggle_links_action.text() == "Hide Links"


def test_toggle_links_action_hides_links_and_flips_label(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)
    link_id = next(iter(window.document.links))
    link_item = window.canvas_scene._link_items[link_id]
    assert link_item.isVisible()

    window.toggle_links_action.trigger()

    assert not link_item.isVisible()
    assert window.toggle_links_action.text() == "Show Links"

    window.toggle_links_action.trigger()

    assert link_item.isVisible()
    assert window.toggle_links_action.text() == "Hide Links"


def test_status_bar_shows_links_on_by_default(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.links_status_label.text() == "Links: On"
    label_type = type(window.links_status_label)
    assert window.links_status_label in window.statusBar().findChildren(label_type)


def test_status_bar_reflects_toggling_links_visibility(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window.toggle_links_action.trigger()
    assert window.links_status_label.text() == "Links: Off"

    window.toggle_links_action.trigger()
    assert window.links_status_label.text() == "Links: On"


def test_clickable_label_emits_clicked_on_left_button_press(qtbot):
    label = _ClickableLabel()
    qtbot.addWidget(label)
    received = []
    label.clicked.connect(lambda: received.append(True))

    event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(0, 0),
        QPointF(0, 0),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    label.mousePressEvent(event)

    assert received == [True]


def test_clickable_label_ignores_right_button_press(qtbot):
    label = _ClickableLabel()
    qtbot.addWidget(label)
    received = []
    label.clicked.connect(lambda: received.append(True))

    event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(0, 0),
        QPointF(0, 0),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
    )
    label.mousePressEvent(event)

    assert received == []


def test_status_bar_shows_emphasized_when_links_are_emphasized(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window.emphasize_links_action.setChecked(True)

    assert window.links_status_label.text() == "Links: Emphasized"


def test_links_status_label_click_cycles_off_on_emphasized(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.links_status_label.text() == "Links: On"

    window.links_status_label.clicked.emit()
    assert window.links_status_label.text() == "Links: Emphasized"
    assert window.emphasize_links_action.isChecked()

    window.links_status_label.clicked.emit()
    assert window.links_status_label.text() == "Links: Off"
    assert window.toggle_links_action.text() == "Show Links"

    window.links_status_label.clicked.emit()
    assert window.links_status_label.text() == "Links: On"
    assert not window.emphasize_links_action.isChecked()


def test_turning_emphasize_on_while_hidden_also_shows_links(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.toggle_links_action.trigger()  # hide
    assert window.links_status_label.text() == "Links: Off"

    window.emphasize_links_action.setChecked(True)

    assert window._links_visible
    assert window.links_status_label.text() == "Links: Emphasized"
    assert window.toggle_links_action.text() == "Hide Links"


def test_hiding_links_while_emphasized_clears_emphasis(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.emphasize_links_action.setChecked(True)
    assert window.links_status_label.text() == "Links: Emphasized"

    window.toggle_links_action.trigger()  # hide

    assert not window._links_emphasized
    assert not window.emphasize_links_action.isChecked()
    assert window.links_status_label.text() == "Links: Off"


def test_view_menu_has_emphasize_links_action(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.emphasize_links_action.isCheckable() is True
    assert window.emphasize_links_action.shortcut() == QKeySequence("Ctrl+Shift+K")
    view_menu = next(
        action.menu() for action in window.menuBar().actions() if action.text() == "&View"
    )
    assert window.emphasize_links_action in view_menu.actions()


def test_emphasize_links_action_toggles_glow_on_every_link(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)
    link_id = next(iter(window.document.links))
    link_item = window.canvas_scene._link_items[link_id]

    window.emphasize_links_action.setChecked(True)
    assert link_item.graphicsEffect() is not None

    window.emphasize_links_action.setChecked(False)
    assert link_item.graphicsEffect() is None


def test_links_menu_has_styling_submenus(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    links_menu = next(
        action.menu() for action in window.menuBar().actions() if action.text() == "&Links"
    )
    styling_menu = next(
        action.menu() for action in links_menu.actions() if action.text() == "Styling"
    )
    submenu_labels = [action.text() for action in styling_menu.actions()]
    assert "Line Weight" in submenu_labels
    assert "Line Color" in submenu_labels


def test_line_weight_menu_reflects_current_theme_weight(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window._update_line_weight_menu()

    current = window.document.theme.link_weight
    assert window._line_weight_actions[current].isChecked()
    assert all(
        not action.isChecked()
        for weight, action in window._line_weight_actions.items()
        if weight != current
    )


def test_selecting_a_line_weight_pushes_undoable_command(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window._on_change_link_weight(5)

    assert window.document.theme.link_weight == 5
    assert window.undo_stack.canUndo()

    window.undo_stack.undo()
    assert window.document.theme.link_weight == 2


def test_selecting_the_same_line_weight_does_not_push_a_command(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window._on_change_link_weight(window.document.theme.link_weight)

    assert window.undo_stack.canUndo() is False


def test_line_color_menu_reflects_current_theme_mode(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window._update_line_color_menu()

    assert window._line_color_actions["theme"].isChecked()
    assert not window._line_color_actions["white"].isChecked()
    assert not window._line_color_actions["black"].isChecked()


def test_selecting_a_line_color_mode_pushes_undoable_command(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window._on_change_link_color_mode("white")

    assert window.document.theme.link_color_mode == "white"
    assert window.undo_stack.canUndo()

    window.undo_stack.undo()
    assert window.document.theme.link_color_mode == "theme"


def test_selecting_the_same_line_color_mode_does_not_push_a_command(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window._on_change_link_color_mode(window.document.theme.link_color_mode)

    assert window.undo_stack.canUndo() is False


def test_default_line_ending_menu_reflects_current_document_default(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window._update_default_line_ending_menu()

    assert window._default_line_ending_actions["none"].isChecked()
    assert not window._default_line_ending_actions["both"].isChecked()


def test_selecting_a_default_line_ending_pushes_undoable_command(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window._on_change_default_line_ending("both")

    assert window.document.default_line_ending == "both"
    assert window.undo_stack.canUndo()

    window.undo_stack.undo()
    assert window.document.default_line_ending == "none"


def test_selecting_the_same_default_line_ending_does_not_push_a_command(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window._on_change_default_line_ending(window.document.default_line_ending)

    assert window.undo_stack.canUndo() is False


def test_link_requested_uses_document_default_line_ending(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)
    window.document.set_default_line_ending("both")

    window._on_link_requested("c_4f9a1b2c", "c_1a2b3c4d")

    new_link = next(
        link
        for link in window.document.links.values()
        if link.source == "c_4f9a1b2c" and link.target == "c_1a2b3c4d"
    )
    assert new_link.line_ending == "both"


def _document_with_two_links() -> Document:
    document = Document(name="Link Endings Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    document.add_card(Card(id="c_2", x=300.0, y=0.0))
    document.add_card(Card(id="c_3", x=600.0, y=0.0))
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    document.add_link(Link(id="l_2", source="c_2", target="c_3"))
    return document


def test_links_menu_has_line_endings_submenu(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    links_menu = next(
        action.menu() for action in window.menuBar().actions() if action.text() == "&Links"
    )
    assert window.link_line_endings_menu.menuAction() in links_menu.actions()


def test_line_endings_menu_disabled_with_no_link_selected(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window._set_document(_document_with_two_links(), path=None)

    window._update_line_endings_menu()

    assert not window.link_line_endings_menu.menuAction().isEnabled()


def test_line_endings_menu_enabled_and_checked_for_a_single_selected_link(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window._set_document(_document_with_two_links(), path=None)
    window.document.set_link_line_ending("l_1", "to_target")
    window.canvas_scene._link_items["l_1"].setSelected(True)

    window._update_line_endings_menu()

    assert window.link_line_endings_menu.menuAction().isEnabled()
    assert window._line_ending_actions["to_target"].isChecked()


def test_line_endings_menu_unchecked_for_a_mixed_ending_selection(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window._set_document(_document_with_two_links(), path=None)
    window.document.set_link_line_ending("l_1", "to_target")
    window.document.set_link_line_ending("l_2", "both")
    window.canvas_scene._link_items["l_1"].setSelected(True)
    window.canvas_scene._link_items["l_2"].setSelected(True)

    window._update_line_endings_menu()

    assert not any(action.isChecked() for action in window._line_ending_actions.values())


def test_selecting_a_line_ending_pushes_command_for_selected_links(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window._set_document(_document_with_two_links(), path=None)
    window.canvas_scene._link_items["l_1"].setSelected(True)
    window.canvas_scene._link_items["l_2"].setSelected(True)

    window._on_change_line_endings("both")

    assert window.document.get_link("l_1").line_ending == "both"
    assert window.document.get_link("l_2").line_ending == "both"
    assert window.undo_stack.canUndo()

    window.undo_stack.undo()
    assert window.document.get_link("l_1").line_ending == "none"
    assert window.document.get_link("l_2").line_ending == "none"


def test_selecting_a_line_ending_with_nothing_selected_does_not_push(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window._set_document(_document_with_two_links(), path=None)

    window._on_change_line_endings("both")

    assert window.undo_stack.canUndo() is False


def test_mixed_card_and_link_selection_applies_only_to_the_link(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window._set_document(_document_with_two_links(), path=None)
    window.canvas_scene.item_for_card("c_1").setSelected(True)
    window.canvas_scene._link_items["l_1"].setSelected(True)

    window._on_change_line_endings("both")

    assert window.document.get_link("l_1").line_ending == "both"
    assert window.undo_stack.canUndo()


def test_view_menu_has_show_color_key_action(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    view_menu = next(
        action.menu() for action in window.menuBar().actions() if action.text() == "&View"
    )
    assert window.toggle_color_key_action in view_menu.actions()
    assert window.toggle_color_key_action.isCheckable() is True


def test_toggle_color_key_action_starts_unchecked_on_a_new_document(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.toggle_color_key_action.isChecked() is False
    assert window.document.color_key_visible is False


def test_toggling_color_key_action_updates_document_and_marks_dirty(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window.toggle_color_key_action.setChecked(True)

    assert window.document.color_key_visible is True
    assert window.document.dirty is True

    window.toggle_color_key_action.setChecked(False)

    assert window.document.color_key_visible is False


def test_opening_a_document_syncs_the_color_key_checkbox(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    other = Document(name="Other")
    other.set_color_key_visible(True)

    window._set_document(other, path=None)

    assert window.toggle_color_key_action.isChecked() is True


def test_links_hidden_state_persists_across_document_switch(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)
    window.toggle_links_action.trigger()
    assert window.toggle_links_action.text() == "Show Links"

    document = Document(name="Second")
    document.add_card(Card(id="c_1"))
    document.add_card(Card(id="c_2"))
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    window._set_document(document, path=None)

    link_item = window.canvas_scene._link_items["l_1"]
    assert not link_item.isVisible()
    assert window.toggle_links_action.text() == "Show Links"


def test_edit_menu_has_select_linked_action_under_select_all(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    edit_menu = next(
        action.menu() for action in window.menuBar().actions() if action.text() == "&Edit"
    )
    action_texts = [action.text() for action in edit_menu.actions()]
    assert action_texts.index("Select &Linked") == action_texts.index("Select &All") + 1


def test_select_linked_action_disabled_with_no_canvas_selection(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)

    window._update_select_linked_enabled()

    assert not window.select_linked_action.isEnabled()


def test_select_linked_action_enabled_once_a_card_is_selected(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)
    card_id = next(iter(window.document.cards))
    window.canvas_scene.item_for_card(card_id).setSelected(True)

    window._update_select_linked_enabled()

    assert window.select_linked_action.isEnabled()


def test_select_linked_action_selects_graph_and_switches_to_canvas(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)
    card_ids = list(window.document.cards)
    window.document.add_link(Link(id="l_test", source=card_ids[0], target=card_ids[1]))
    window.view_stack.setCurrentWidget(window.list_view)
    window.canvas_scene.item_for_card(card_ids[0]).setSelected(True)

    window._on_select_linked()

    assert window.view_stack.currentWidget() is window.canvas_view
    assert window.canvas_scene.item_for_card(card_ids[0]).isSelected()
    assert window.canvas_scene.item_for_card(card_ids[1]).isSelected()


def test_edit_menu_has_pin_action_under_select_linked(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    edit_menu = next(
        action.menu() for action in window.menuBar().actions() if action.text() == "&Edit"
    )
    assert window.pin_action in edit_menu.actions()
    assert window.pin_action.shortcut() == QKeySequence("Ctrl+Shift+P")


def test_pin_action_disabled_with_no_selection(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)

    window._update_pin_action()

    assert not window.pin_action.isEnabled()


def test_pin_action_reads_pin_cards_for_unpinned_selection(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)
    card_id = next(iter(window.document.cards))
    window.canvas_scene.item_for_card(card_id).setSelected(True)

    window._update_pin_action()

    assert window.pin_action.isEnabled()
    assert window.pin_action.text() == "Pin Card"


def test_pin_action_reads_unpin_cards_when_selection_all_pinned(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)
    card_id = next(iter(window.document.cards))
    window.document.set_card_pinned(card_id, True)
    window.canvas_scene.item_for_card(card_id).setSelected(True)

    window._update_pin_action()

    assert window.pin_action.text() == "Unpin Card"


def test_pin_action_reads_plural_for_multi_selection(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)
    card_ids = list(window.document.cards)[:2]
    for card_id in card_ids:
        window.canvas_scene.item_for_card(card_id).setSelected(True)

    window._update_pin_action()

    assert window.pin_action.text() == "Pin Card(s)"


def test_on_toggle_pin_pins_selected_cards(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)
    card_id = next(iter(window.document.cards))
    window.canvas_scene.item_for_card(card_id).setSelected(True)

    window._on_toggle_pin()

    assert window.document.get_card(card_id).pinned is True
    assert window.undo_stack.canUndo()


def test_on_toggle_pin_unpins_mixed_selection_only_if_all_pinned(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)
    card_ids = list(window.document.cards)[:2]
    window.document.set_card_pinned(card_ids[0], True)
    for card_id in card_ids:
        window.canvas_scene.item_for_card(card_id).setSelected(True)

    window._on_toggle_pin()  # mixed selection -> pins everyone

    assert window.document.get_card(card_ids[0]).pinned is True
    assert window.document.get_card(card_ids[1]).pinned is True

    window._on_toggle_pin()  # now all pinned -> unpins everyone

    assert window.document.get_card(card_ids[0]).pinned is False
    assert window.document.get_card(card_ids[1]).pinned is False


def test_on_toggle_pin_does_nothing_with_no_selection(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)

    window._on_toggle_pin()  # must not raise


def _document_with_stack() -> Document:
    document = Document(name="Stack Test")
    document.add_card(Card(id="c_1", stack_id="s_1"))
    document.add_card(Card(id="c_2", stack_id="s_1"))
    document.add_stack(Stack(id="s_1", label="Chapter 1", card_ids=["c_1", "c_2"]))
    return document


def test_edit_menu_has_delete_stack_action(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    edit_menu = next(
        action.menu() for action in window.menuBar().actions() if action.text() == "&Edit"
    )
    assert window.delete_stack_action in edit_menu.actions()


def test_delete_stack_action_disabled_with_no_stack_selected(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window._set_document(_document_with_stack(), path=None)

    window._update_delete_stack_action()

    assert not window.delete_stack_action.isEnabled()


def test_delete_stack_action_enabled_and_labeled_singular_with_stack_selected(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window._set_document(_document_with_stack(), path=None)
    window.canvas_scene.item_for_stack("s_1").setSelected(True)

    window._update_delete_stack_action()

    assert window.delete_stack_action.isEnabled()
    assert window.delete_stack_action.text() == "Delete Stack"


def test_on_delete_stack_confirmed_removes_stack_and_cards(qtbot, monkeypatch):
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.Yes)
    window = MainWindow()
    qtbot.addWidget(window)
    window._set_document(_document_with_stack(), path=None)
    window.canvas_scene.item_for_stack("s_1").setSelected(True)

    window._on_delete_stack()

    assert "s_1" not in window.document.stacks
    assert window.document.cards == {}
    assert window.undo_stack.canUndo()

    window.undo_stack.undo()
    assert set(window.document.cards) == {"c_1", "c_2"}
    assert window.document.get_stack("s_1").card_ids == ["c_1", "c_2"]


def test_on_delete_stack_cancelled_leaves_stack_intact(qtbot, monkeypatch):
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.Cancel)
    window = MainWindow()
    qtbot.addWidget(window)
    window._set_document(_document_with_stack(), path=None)
    window.canvas_scene.item_for_stack("s_1").setSelected(True)

    window._on_delete_stack()

    assert "s_1" in window.document.stacks
    assert window.undo_stack.canUndo() is False


def test_on_delete_stack_does_nothing_with_no_selection(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window._set_document(_document_with_stack(), path=None)

    window._on_delete_stack()  # must not raise

    assert "s_1" in window.document.stacks


def test_on_delete_stack_multi_stack_selection_uses_one_outer_macro(qtbot, monkeypatch):
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.Yes)
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Stack Test")
    document.add_card(Card(id="c_1", stack_id="s_1"))
    document.add_card(Card(id="c_2", stack_id="s_2"))
    document.add_stack(Stack(id="s_1", card_ids=["c_1"]))
    document.add_stack(Stack(id="s_2", card_ids=["c_2"]))
    window._set_document(document, path=None)
    window.canvas_scene.item_for_stack("s_1").setSelected(True)
    window.canvas_scene.item_for_stack("s_2").setSelected(True)

    window._on_delete_stack()

    assert window.document.stacks == {}
    assert window.document.cards == {}

    window.undo_stack.undo()  # one undo step for both stacks
    assert set(window.document.stacks) == {"s_1", "s_2"}
    assert set(window.document.cards) == {"c_1", "c_2"}


def test_arrange_menu_has_gather_stacks_action(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    arrange_menu = next(
        action.menu() for action in window.menuBar().actions() if action.text() == "&Arrange"
    )
    assert window.gather_stacks_action in arrange_menu.actions()


def test_gather_stacks_disabled_with_fewer_than_two_stacks(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Stack Test")
    document.add_stack(Stack(id="s_1"))
    window._set_document(document, path=None)

    window._update_arrange_actions_enabled()

    assert not window.gather_stacks_action.isEnabled()


def test_gather_stacks_enabled_with_two_or_more_stacks(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Stack Test")
    document.add_stack(Stack(id="s_1"))
    document.add_stack(Stack(id="s_2"))
    window._set_document(document, path=None)

    window._update_arrange_actions_enabled()

    assert window.gather_stacks_action.isEnabled()


def test_on_gather_stacks_repositions_and_is_undoable(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Stack Test")
    document.add_stack(Stack(id="s_1", x=0.0, y=0.0))
    document.add_stack(Stack(id="s_2", x=900.0, y=900.0))
    window._set_document(document, path=None)
    old_position = (window.document.get_stack("s_2").x, window.document.get_stack("s_2").y)

    window._on_gather_stacks()

    assert window.undo_stack.canUndo()
    new_position = (window.document.get_stack("s_2").x, window.document.get_stack("s_2").y)
    assert new_position != old_position

    window.undo_stack.undo()
    assert (window.document.get_stack("s_2").x, window.document.get_stack("s_2").y) == old_position


_Bbox = tuple[float, float, float, float]


def _bboxes_overlap(a: _Bbox, b: _Bbox) -> bool:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    return not (ax2 <= bx1 or ax1 >= bx2 or ay2 <= by1 or ay1 >= by2)


def test_on_gather_stacks_avoids_existing_cards(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Stack Test")
    # A loose card sitting right where the stacks' fresh tile layout would
    # otherwise start (tile always begins near the origin).
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    document.add_stack(Stack(id="s_1", x=900.0, y=0.0))
    document.add_stack(Stack(id="s_2", x=900.0, y=900.0))
    window._set_document(document, path=None)

    window._on_gather_stacks()

    card_bbox = positions_bbox({"c_1": (0.0, 0.0)})
    new_stack_bbox = positions_bbox(
        {
            "s_1": (window.document.get_stack("s_1").x, window.document.get_stack("s_1").y),
            "s_2": (window.document.get_stack("s_2").x, window.document.get_stack("s_2").y),
        }
    )
    assert not _bboxes_overlap(card_bbox, new_stack_bbox)


def test_on_gather_stacks_defaults_to_gathering_left(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window._settings.gather_stacks_edge == "left"
    document = Document(name="Stack Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    document.add_stack(Stack(id="s_1", x=900.0, y=900.0))
    document.add_stack(Stack(id="s_2", x=900.0, y=1200.0))
    window._set_document(document, path=None)

    window._on_gather_stacks()

    assert (window.document.get_stack("s_1").x, window.document.get_stack("s_1").y) == (
        -240.0,
        0.0,
    )
    assert (window.document.get_stack("s_2").x, window.document.get_stack("s_2").y) == (
        -240.0,
        160.0,
    )


def test_on_gather_stacks_honors_right_edge_setting(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window._settings.gather_stacks_edge = "right"
    document = Document(name="Stack Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    document.add_stack(Stack(id="s_1"))
    document.add_stack(Stack(id="s_2"))
    window._set_document(document, path=None)

    window._on_gather_stacks()

    assert (window.document.get_stack("s_1").x, window.document.get_stack("s_1").y) == (
        240.0,
        0.0,
    )
    assert (window.document.get_stack("s_2").x, window.document.get_stack("s_2").y) == (
        240.0,
        160.0,
    )


def test_on_gather_stacks_honors_top_edge_setting(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window._settings.gather_stacks_edge = "top"
    document = Document(name="Stack Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    document.add_stack(Stack(id="s_1"))
    document.add_stack(Stack(id="s_2"))
    window._set_document(document, path=None)

    window._on_gather_stacks()

    assert (window.document.get_stack("s_1").x, window.document.get_stack("s_1").y) == (
        0.0,
        -160.0,
    )
    assert (window.document.get_stack("s_2").x, window.document.get_stack("s_2").y) == (
        240.0,
        -160.0,
    )


def test_on_gather_stacks_honors_bottom_edge_setting(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window._settings.gather_stacks_edge = "bottom"
    document = Document(name="Stack Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    document.add_stack(Stack(id="s_1"))
    document.add_stack(Stack(id="s_2"))
    window._set_document(document, path=None)

    window._on_gather_stacks()

    assert (window.document.get_stack("s_1").x, window.document.get_stack("s_1").y) == (
        0.0,
        160.0,
    )
    assert (window.document.get_stack("s_2").x, window.document.get_stack("s_2").y) == (
        240.0,
        160.0,
    )


def test_on_gather_stacks_with_no_cards_anchors_at_origin(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Stack Test")
    document.add_stack(Stack(id="s_1", x=900.0, y=900.0))
    document.add_stack(Stack(id="s_2", x=-500.0, y=-500.0))
    window._set_document(document, path=None)

    window._on_gather_stacks()

    assert (window.document.get_stack("s_1").x, window.document.get_stack("s_1").y) == (0.0, 0.0)
    assert (window.document.get_stack("s_2").x, window.document.get_stack("s_2").y) == (0.0, 160.0)


def test_open_settings_accepted_updates_gather_stacks_edge(qtbot, monkeypatch):
    def fake_exec(self):
        position = self.gather_stacks_edge_combo.findData("bottom")
        self.gather_stacks_edge_combo.setCurrentIndex(position)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(SettingsDialog, "exec", fake_exec)
    window = MainWindow()
    qtbot.addWidget(window)

    window._on_open_settings()

    assert window._settings.gather_stacks_edge == "bottom"


def test_on_gather_stacks_does_nothing_with_fewer_than_two_stacks(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Stack Test")
    document.add_stack(Stack(id="s_1"))
    window._set_document(document, path=None)

    window._on_gather_stacks()  # must not raise

    assert window.undo_stack.canUndo() is False


def test_arrange_actions_ignore_stacked_cards(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Arrange Test")
    document.add_card(Card(id="c_1", stack_id="s_1"))
    document.add_card(Card(id="c_2", stack_id="s_1"))
    document.add_stack(Stack(id="s_1", card_ids=["c_1", "c_2"]))

    window._set_document(document, path=None)
    window._update_arrange_actions_enabled()

    # Both cards are inside a stack (not on canvas as loose cards) — same
    # as if there were zero unstacked, unpinned cards to arrange.
    assert not any(action.isEnabled() for action in _arrange_actions(window))


def test_run_auto_arrange_does_not_move_stacked_cards(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Arrange Test")
    document.add_card(Card(id="c_1", x=500.0, y=500.0, stack_id="s_1"))
    document.add_card(Card(id="c_2"))
    document.add_card(Card(id="c_3"))
    document.add_stack(Stack(id="s_1", card_ids=["c_1"]))
    window._set_document(document, path=None)

    window._run_auto_arrange("tile")

    # c_1 is inside a stack — untouched. c_2/c_3 are the two free unstacked
    # cards that make Auto-Arrange eligible to run at all, and do get
    # rearranged as a result.
    assert (window.document.get_card("c_1").x, window.document.get_card("c_1").y) == (500.0, 500.0)
    assert window.undo_stack.canUndo()


def test_run_auto_arrange_avoids_existing_stacks(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Arrange Test")
    # A Stack box sitting right where a fresh tile layout would otherwise
    # start (tile always begins near the origin).
    document.add_stack(Stack(id="s_1", x=0.0, y=0.0))
    document.add_card(Card(id="c_1"))
    document.add_card(Card(id="c_2"))
    document.add_card(Card(id="c_3"))
    window._set_document(document, path=None)

    window._run_auto_arrange("tile")

    stack_bbox = positions_bbox({"s_1": (0.0, 0.0)})
    new_card_bbox = positions_bbox(
        {cid: (c.x, c.y) for cid, c in window.document.cards.items()}
    )
    assert not _bboxes_overlap(stack_bbox, new_card_bbox)


def test_arrange_menu_has_tidy_and_sweep_to_edges_actions(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    arrange_menu = next(
        action.menu() for action in window.menuBar().actions() if action.text() == "&Arrange"
    )
    assert window.tidy_to_edges_action in arrange_menu.actions()
    assert window.sweep_to_edges_action in arrange_menu.actions()


def test_edges_actions_disabled_with_nothing_to_move(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window._update_arrange_actions_enabled()

    assert not window.tidy_to_edges_action.isEnabled()
    assert not window.sweep_to_edges_action.isEnabled()


def test_edges_actions_enabled_with_a_single_unpinned_card(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Edges Test")
    document.add_card(Card(id="c_1"))
    window._set_document(document, path=None)

    window._update_arrange_actions_enabled()

    assert window.tidy_to_edges_action.isEnabled()
    assert window.sweep_to_edges_action.isEnabled()


def test_edges_actions_enabled_with_only_a_single_stack(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Edges Test")
    document.add_stack(Stack(id="s_1"))
    window._set_document(document, path=None)

    window._update_arrange_actions_enabled()

    assert window.tidy_to_edges_action.isEnabled()
    assert window.sweep_to_edges_action.isEnabled()


def test_edges_arrange_does_nothing_when_there_is_nothing_to_move(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    window._run_edges_arrange("tidy")  # must not raise

    assert window.undo_stack.canUndo() is False


def test_tidy_to_edges_leaves_pinned_cards_untouched(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Edges Test")
    document.add_card(Card(id="pinned_1", x=0.0, y=0.0, pinned=True))
    document.add_card(Card(id="c_1", x=900.0, y=900.0))
    document.add_card(Card(id="c_2", x=-900.0, y=-900.0))
    window._set_document(document, path=None)

    window._run_edges_arrange("tidy")

    assert (window.document.get_card("pinned_1").x, window.document.get_card("pinned_1").y) == (
        0.0,
        0.0,
    )
    assert window.undo_stack.canUndo()


def test_tidy_to_edges_moves_unpinned_cards(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Edges Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    document.add_card(Card(id="c_2", x=10.0, y=10.0))
    window._set_document(document, path=None)

    window._run_edges_arrange("tidy")

    assert (window.document.get_card("c_1").x, window.document.get_card("c_1").y) != (0.0, 0.0)


def test_tidy_to_edges_undoes_cards_and_stacks_in_one_step(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Edges Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    document.add_stack(Stack(id="s_1", x=900.0, y=900.0))
    window._set_document(document, path=None)
    old_card = (window.document.get_card("c_1").x, window.document.get_card("c_1").y)
    old_stack = (window.document.get_stack("s_1").x, window.document.get_stack("s_1").y)

    window._run_edges_arrange("tidy")

    assert (window.document.get_card("c_1").x, window.document.get_card("c_1").y) != old_card
    assert (window.document.get_stack("s_1").x, window.document.get_stack("s_1").y) != old_stack

    window.undo_stack.undo()  # one undo step for both cards and stacks

    assert (window.document.get_card("c_1").x, window.document.get_card("c_1").y) == old_card
    assert (window.document.get_stack("s_1").x, window.document.get_stack("s_1").y) == old_stack


def test_tidy_to_edges_stacks_never_overlap_the_new_card_layout(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Edges Test")
    for i in range(3):
        document.add_card(Card(id=f"c_{i}", x=float(i * 10), y=float(i * 10)))
    document.add_stack(Stack(id="s_1"))
    document.add_stack(Stack(id="s_2"))
    window._set_document(document, path=None)

    window._run_edges_arrange("tidy")

    card_bbox = positions_bbox({cid: (c.x, c.y) for cid, c in window.document.cards.items()})
    stack_bbox = positions_bbox({sid: (s.x, s.y) for sid, s in window.document.stacks.items()})
    assert not _bboxes_overlap(card_bbox, stack_bbox)


def test_sweep_to_edges_is_undoable(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Edges Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    window._set_document(document, path=None)

    window._run_edges_arrange("sweep")

    assert window.undo_stack.canUndo()


class _FakeClipboard:
    """Stands in for QApplication.clipboard() in tests so pytest never
    touches the developer's real system clipboard."""

    def __init__(self) -> None:
        self._mime: QMimeData | None = None

    def setMimeData(self, mime: QMimeData) -> None:
        self._mime = mime

    def mimeData(self) -> QMimeData | None:
        return self._mime

    def setText(self, text: str) -> None:
        mime = QMimeData()
        mime.setText(text)
        self._mime = mime


@pytest.fixture
def fake_clipboard(monkeypatch):
    clipboard = _FakeClipboard()
    monkeypatch.setattr(MainWindow, "_clipboard", lambda self: clipboard)
    return clipboard


def test_arrange_menu_has_no_effect_on_clipboard_actions_smoke(qtbot, fake_clipboard):
    # Sanity check the fixture itself: a fresh window's Edit menu has the
    # three new actions, disabled with nothing selected and nothing on
    # the (fake) clipboard.
    window = MainWindow()
    qtbot.addWidget(window)

    window._update_clipboard_actions_enabled()

    assert not window.cut_action.isEnabled()
    assert not window.copy_action.isEnabled()
    assert not window.paste_action.isEnabled()


def test_cut_copy_paste_actions_enabled_with_canvas_selection(qtbot, fake_clipboard):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Test")
    document.add_card(Card(id="c_1"))
    window._set_document(document, path=None)
    window.canvas_scene.item_for_card("c_1").setSelected(True)

    window._update_clipboard_actions_enabled()

    assert window.cut_action.isEnabled()
    assert window.copy_action.isEnabled()


def test_paste_action_enabled_once_clipboard_has_text(qtbot, fake_clipboard):
    window = MainWindow()
    qtbot.addWidget(window)
    window._update_clipboard_actions_enabled()
    assert not window.paste_action.isEnabled()

    fake_clipboard.setText("hello")
    window._update_clipboard_actions_enabled()
    assert window.paste_action.isEnabled()


def test_copy_puts_plain_text_and_internal_payload_on_clipboard(qtbot, fake_clipboard):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="Hello", color_slot=document.theme.slots[0].id))
    window._set_document(document, path=None)
    window.canvas_scene.item_for_card("c_1").setSelected(True)

    window._on_copy()

    mime = fake_clipboard.mimeData()
    assert mime.text() == "Hello"
    assert mime.hasFormat(CLIPBOARD_MIME_TYPE)
    payload = json.loads(bytes(mime.data(CLIPBOARD_MIME_TYPE)).decode("utf-8"))
    assert [c["text"] for c in payload["cards"]] == ["Hello"]


def test_copy_from_list_view_reads_list_selection(qtbot, fake_clipboard):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="Row One", color_slot=document.theme.slots[0].id))
    window._set_document(document, path=None)
    window.view_stack.setCurrentWidget(window.list_view)
    row = window.card_table_model.row_for_card_id("c_1")
    window.list_view.table_view.selectRow(row)

    window._on_copy()

    mime = fake_clipboard.mimeData()
    assert mime.text() == "Row One"


def test_copy_includes_a_selected_stacks_member_cards(qtbot, fake_clipboard):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="First", stack_id="s_1"))
    document.add_card(Card(id="c_2", text="Second", stack_id="s_1"))
    document.add_stack(Stack(id="s_1", card_ids=["c_1", "c_2"], label="Group"))
    window._set_document(document, path=None)
    window.canvas_scene.item_for_stack("s_1").setSelected(True)

    window._on_copy()

    mime = fake_clipboard.mimeData()
    assert mime.text() == "IndexCards Stack: Group\n* First\n* Second"
    payload = json.loads(bytes(mime.data(CLIPBOARD_MIME_TYPE)).decode("utf-8"))
    assert payload["stacks"][0]["label"] == "Group"


def test_cut_deletes_source_and_is_undoable(qtbot, fake_clipboard):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="Gone Soon"))
    window._set_document(document, path=None)
    window.canvas_scene.item_for_card("c_1").setSelected(True)

    window._on_cut()

    assert "c_1" not in window.document.cards
    assert fake_clipboard.mimeData().text() == "Gone Soon"

    window.undo_stack.undo()
    assert "c_1" in window.document.cards


def test_cut_of_stack_deletes_stack_and_members_undoably(qtbot, fake_clipboard):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Test")
    document.add_card(Card(id="c_1", stack_id="s_1"))
    document.add_card(Card(id="c_2", stack_id="s_1"))
    document.add_stack(Stack(id="s_1", card_ids=["c_1", "c_2"]))
    window._set_document(document, path=None)
    window.canvas_scene.item_for_stack("s_1").setSelected(True)

    window._on_cut()

    assert window.document.cards == {}
    assert window.document.stacks == {}

    window.undo_stack.undo()
    assert set(window.document.cards) == {"c_1", "c_2"}
    assert "s_1" in window.document.stacks


def test_cut_mixed_selection_is_one_undo_step(qtbot, fake_clipboard):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Test")
    document.add_card(Card(id="c_1"))
    document.add_card(Card(id="c_2", stack_id="s_1"))
    document.add_stack(Stack(id="s_1", card_ids=["c_2"]))
    window._set_document(document, path=None)
    window.canvas_scene.item_for_card("c_1").setSelected(True)
    window.canvas_scene.item_for_stack("s_1").setSelected(True)

    window._on_cut()

    assert window.document.cards == {}
    assert window.document.stacks == {}

    window.undo_stack.undo()
    assert set(window.document.cards) == {"c_1", "c_2"}
    assert "s_1" in window.document.stacks


def test_paste_internal_format_creates_new_card_centered_on_viewport(qtbot, fake_clipboard):
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(1000, 700)
    window.show()
    qtbot.waitActive(window)
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="Cut Me", color_slot=document.theme.slots[0].id))
    window._set_document(document, path=None)
    window.canvas_scene.item_for_card("c_1").setSelected(True)
    window._on_cut()  # nothing left on the canvas to nudge away from

    window._on_paste()

    assert len(window.document.cards) == 1
    pasted = next(iter(window.document.cards.values()))
    assert pasted.text == "Cut Me"

    width, height = 200, 120  # DEFAULT_CARD_SIZE
    target_center = window.canvas_view.mapToScene(window.canvas_view.viewport().rect().center())
    assert pasted.x + width / 2 == pytest.approx(target_center.x())
    assert pasted.y + height / 2 == pytest.approx(target_center.y())

    assert window.undo_stack.canUndo()
    window.undo_stack.undo()
    assert pasted.id not in window.document.cards


def test_paste_nudges_away_from_the_still_present_original(qtbot, fake_clipboard):
    # The bug report's scenario: copying (not cutting) a card, then
    # pasting, lands the recentered copy right on top of the original --
    # it must get nudged clear rather than perfectly overlapping it.
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(1000, 700)
    window.show()
    qtbot.waitActive(window)
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="Copy Me", color_slot=document.theme.slots[0].id))
    window._set_document(document, path=None)
    window.canvas_scene.item_for_card("c_1").setSelected(True)
    window._on_copy()

    before_ids = set(window.document.cards)
    window._on_paste()

    new_ids = set(window.document.cards) - before_ids
    assert len(new_ids) == 1
    pasted = window.document.get_card(next(iter(new_ids)))
    original = window.document.get_card("c_1")

    width, height = 200, 120  # DEFAULT_CARD_SIZE
    other = [(original.x, original.y)]
    fraction = _max_overlap_fraction((pasted.x, pasted.y), other, width, height)
    assert fraction < 0.5


def test_repeated_pastes_step_diagonally_away_from_each_other(qtbot, fake_clipboard):
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(1000, 700)
    window.show()
    qtbot.waitActive(window)
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="Original"))
    window._set_document(document, path=None)
    window.canvas_scene.item_for_card("c_1").setSelected(True)
    window._on_copy()

    window._on_paste()
    window._on_paste()
    window._on_paste()

    width, height = 200, 120  # DEFAULT_CARD_SIZE
    positions = [(c.x, c.y) for c in window.document.cards.values()]
    assert len(positions) == 4  # original + 3 pastes
    assert len(set(positions)) == 4  # no two cards share a position

    for i, pos_a in enumerate(positions):
        others = positions[:i] + positions[i + 1 :]
        assert _max_overlap_fraction(pos_a, others, width, height) < 0.5


def test_paste_internal_format_recreates_a_stack(qtbot, fake_clipboard):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Test")
    document.add_card(Card(id="c_1", stack_id="s_1"))
    document.add_card(Card(id="c_2", stack_id="s_1"))
    document.add_stack(Stack(id="s_1", card_ids=["c_1", "c_2"], label="Group"))
    window._set_document(document, path=None)
    window.canvas_scene.item_for_stack("s_1").setSelected(True)
    window._on_copy()

    window._on_paste()

    new_stack_ids = set(window.document.stacks) - {"s_1"}
    assert len(new_stack_ids) == 1
    new_stack = window.document.get_stack(next(iter(new_stack_ids)))
    assert new_stack.label == "Group"
    assert len(new_stack.card_ids) == 2
    assert all(window.document.get_card(cid).stack_id == new_stack.id for cid in new_stack.card_ids)


def test_paste_across_documents_resolves_color_by_hex_or_falls_back(qtbot, fake_clipboard):
    window = MainWindow()
    qtbot.addWidget(window)
    source = Document(name="Source", theme=clone_theme(PRESET_THEMES[0]))
    source.add_card(Card(id="c_1", text="Colorful", color_slot=source.theme.slots[2].id))
    window._set_document(source, path=None)
    window.canvas_scene.item_for_card("c_1").setSelected(True)
    window._on_copy()

    destination = Document(name="Dest", theme=clone_theme(PRESET_THEMES[1]))
    window._set_document(destination, path=None)

    window._on_paste()

    pasted = next(iter(window.document.cards.values()))
    assert pasted.color_slot in {slot.id for slot in destination.theme.slots}


def test_paste_plain_external_text_creates_one_card_per_line(qtbot, fake_clipboard):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Test")
    window._set_document(document, path=None)
    fake_clipboard.setText("Alpha\nBeta\n\nGamma")

    window._on_paste()

    texts = {card.text for card in window.document.cards.values()}
    assert texts == {"Alpha", "Beta", "Gamma"}


def test_paste_with_nothing_usable_on_clipboard_is_a_noop(qtbot, fake_clipboard):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Test")
    window._set_document(document, path=None)

    window._on_paste()  # must not raise

    assert window.document.cards == {}
    assert window.undo_stack.canUndo() is False


# Regression coverage for a real bug: Card.text is stored as markdown (see
# card_item.py's _commit_text), where a hard line break between two blocks
# is a blank-line block separator ("Alpha\n\nBravo"), not a single \n.
# Escaping that raw text verbatim doubled every line break in the exported
# plain text, and naively unescaping back to a single \n on paste-in would
# have silently collapsed a multi-line card onto one line the next time it
# was opened for editing (setMarkdown() treats a lone \n as a soft break
# within one paragraph, not a new block).


def test_copy_exports_one_escaped_newline_per_hard_line_break_not_two(qtbot, fake_clipboard):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Test")
    # Exactly what Card.text holds for a real 3-line card (confirmed via
    # QTextDocument.toMarkdown() on Alpha/Bravo/Charlie blocks, trailing
    # blank block included).
    document.add_card(Card(id="c_1", text="Alpha\n\nBravo\n\nCharlie\n\n"))
    window._set_document(document, path=None)
    window.canvas_scene.item_for_card("c_1").setSelected(True)

    window._on_copy()

    assert fake_clipboard.mimeData().text() == "Alpha\\nBravo\\nCharlie"


def test_paste_of_reexported_text_reconstructs_a_real_three_block_card(qtbot, fake_clipboard):
    # The bug report's exact scenario: copy a hard-line-break card out,
    # paste unchanged into another window (standing in for "another app,
    # then copied again") -- the reconstructed card must still render as
    # three real separate lines, not one line, when next parsed as markdown.
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="Alpha\n\nBravo\n\nCharlie\n\n"))
    window._set_document(document, path=None)
    window.canvas_scene.item_for_card("c_1").setSelected(True)
    window._on_copy()

    window._on_paste()

    new_ids = set(window.document.cards) - {"c_1"}
    pasted = window.document.get_card(next(iter(new_ids)))
    reloaded = QTextDocument()
    reloaded.setMarkdown(pasted.text)
    assert reloaded.blockCount() == 3
    assert reloaded.toPlainText() == "Alpha\nBravo\nCharlie"


def test_paste_of_a_single_reexported_line_still_reconstructs_a_real_multiline_card(
    qtbot, fake_clipboard
):
    # A single physical line containing escaped backslash-n sequences
    # (what a hard-line-break card looks like once exported) must expand
    # into real separate blocks on paste-in, not collapse into one when
    # later opened for editing, and must NOT be split into multiple cards
    # (the backslash-n sequences are not physical newlines).
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Test")
    window._set_document(document, path=None)
    fake_clipboard.setText("Alpha\\nBravo\\nCharlie")

    window._on_paste()

    assert len(window.document.cards) == 1
    pasted = next(iter(window.document.cards.values()))
    reloaded = QTextDocument()
    reloaded.setMarkdown(pasted.text)
    assert reloaded.blockCount() == 3
    assert reloaded.toPlainText() == "Alpha\nBravo\nCharlie"


# Regression coverage for a real bug: a freshly opened/created window's
# Cmd+V did nothing until Edit > Paste had been opened once. Root cause:
# _build_menu()'s one-time enabled-state check ran while self.document was
# still None (it's set afterward, in _set_document during the same
# __init__), so paste_action was forced disabled regardless of what was
# actually on the clipboard -- and nothing re-checked it until some later
# signal (a selection change, a menu open) happened to fire.


def test_new_window_paste_action_enabled_immediately_when_clipboard_already_has_content(
    qtbot, fake_clipboard
):
    # Simulates: something was already copied (e.g. in another window)
    # before this window even opened -- Cmd+N, then Cmd+V should work on
    # the very first press, with no manual refresh and no menu opened.
    fake_clipboard.setText("Copied before this window existed")

    window = MainWindow()
    qtbot.addWidget(window)

    assert window.paste_action.isEnabled()


# Regression coverage for a real bug: a QAction's shortcut only fires while
# the action is actually enabled at that moment. Refreshing enabled state
# only on the Edit menu's aboutToShow meant Cmd+X/C/V silently did nothing
# unless the user had already opened the Edit menu since the last selection
# or clipboard change. These tests deliberately never call
# _update_clipboard_actions_enabled() themselves -- only real signals should
# drive the state, the same way a live keypress would encounter it.


def test_cut_copy_actions_become_enabled_live_on_canvas_selection(qtbot, fake_clipboard):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Test")
    document.add_card(Card(id="c_1"))
    window._set_document(document, path=None)
    assert not window.cut_action.isEnabled()
    assert not window.copy_action.isEnabled()

    window.canvas_scene.item_for_card("c_1").setSelected(True)

    assert window.cut_action.isEnabled()
    assert window.copy_action.isEnabled()

    window.canvas_scene.item_for_card("c_1").setSelected(False)

    assert not window.cut_action.isEnabled()
    assert not window.copy_action.isEnabled()


def test_cut_copy_actions_become_enabled_live_on_list_view_selection(qtbot, fake_clipboard):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Test")
    document.add_card(Card(id="c_1"))
    window._set_document(document, path=None)
    window.view_stack.setCurrentWidget(window.list_view)
    assert not window.cut_action.isEnabled()

    row = window.card_table_model.row_for_card_id("c_1")
    window.list_view.table_view.selectRow(row)

    assert window.cut_action.isEnabled()
    assert window.copy_action.isEnabled()


def test_clipboard_actions_enabled_state_tracks_the_active_tab(qtbot, fake_clipboard):
    # A selected Stack has no List-view representation at all (unlike a
    # card, whose selection syncs across both views), so switching tabs
    # should genuinely change whether Cut/Copy see anything selected.
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Test")
    document.add_card(Card(id="c_1", stack_id="s_1"))
    document.add_stack(Stack(id="s_1", card_ids=["c_1"]))
    window._set_document(document, path=None)
    window.canvas_scene.item_for_stack("s_1").setSelected(True)
    assert window.cut_action.isEnabled()

    window.view_stack.setCurrentWidget(window.list_view)
    assert not window.cut_action.isEnabled()

    window.view_stack.setCurrentWidget(window.canvas_view)
    assert window.cut_action.isEnabled()


def test_paste_action_becomes_enabled_live_immediately_after_copy(qtbot, fake_clipboard):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="Copy Me"))
    window._set_document(document, path=None)
    window.canvas_scene.item_for_card("c_1").setSelected(True)
    assert not window.paste_action.isEnabled()

    window._on_copy()

    assert window.paste_action.isEnabled()


def test_cut_copy_paste_actions_fire_via_trigger_when_enabled(qtbot, fake_clipboard):
    # Exercises the actions the same way a fired keyboard shortcut would
    # (QAction.trigger()), rather than calling the handler methods directly.
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="Shortcut Card"))
    window._set_document(document, path=None)
    window.canvas_scene.item_for_card("c_1").setSelected(True)

    window.copy_action.trigger()
    assert fake_clipboard.mimeData().text() == "Shortcut Card"

    window.cut_action.trigger()
    assert "c_1" not in window.document.cards

    window.paste_action.trigger()
    assert len(window.document.cards) == 1


def test_edit_menu_has_add_to_stack_and_remove_from_stack_actions(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    edit_menu = next(
        action.menu() for action in window.menuBar().actions() if action.text() == "&Edit"
    )
    assert window.add_to_stack_menu.menuAction() in edit_menu.actions()
    assert window.remove_from_stack_action in edit_menu.actions()


def test_add_to_stack_menu_disabled_with_no_canvas_selection(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)

    window._rebuild_add_to_stack_menu()

    assert not window.add_to_stack_menu.menuAction().isEnabled()


def test_add_to_stack_menu_lists_new_stack_and_existing_stacks_when_card_selected(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)
    window.document.add_stack(Stack(id="s_1", label="Chapter 1"))
    card_id = next(iter(window.document.cards))
    window.canvas_scene.item_for_card(card_id).setSelected(True)

    window._rebuild_add_to_stack_menu()

    assert window.add_to_stack_menu.menuAction().isEnabled()
    action_texts = [action.text() for action in window.add_to_stack_menu.actions()]
    assert action_texts[0] == "New Stack..."
    assert "Chapter 1" in action_texts


def test_add_to_stack_new_stack_action_creates_stack_from_selection(qtbot, monkeypatch):
    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *a, **k: ("Chapter 1", True))
    )
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)
    card_id = next(iter(window.document.cards))
    window.canvas_scene.item_for_card(card_id).setSelected(True)

    window._on_add_to_new_stack()

    new_stack_id = window.document.get_card(card_id).stack_id
    assert new_stack_id is not None


def test_card_color_menu_disabled_with_no_canvas_selection(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)

    window._rebuild_card_color_menu()

    assert not window.card_color_menu.menuAction().isEnabled()


def test_card_color_menu_lists_theme_slots_when_card_selected(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)
    card_id = next(iter(window.document.cards))
    window.canvas_scene.item_for_card(card_id).setSelected(True)

    window._rebuild_card_color_menu()

    assert window.card_color_menu.menuAction().isEnabled()
    action_labels = [action.text() for action in window.card_color_menu.actions()]
    expected_labels = [
        slot.label for slot in window.document.theme.slots if not slot.orphaned
    ]
    assert action_labels == expected_labels


def test_card_color_menu_checks_the_uniform_selection_color(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)
    card_ids = list(window.document.cards)
    for card_id in card_ids:
        window.document.set_card_color_slot(card_id, "slot_white")
        window.canvas_scene.item_for_card(card_id).setSelected(True)

    window._rebuild_card_color_menu()

    checked = [action for action in window.card_color_menu.actions() if action.isChecked()]
    assert len(checked) == 1
    assert checked[0].text() == window.document.get_slot("slot_white").label


def test_card_color_menu_checks_nothing_for_a_mixed_selection(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)
    card_ids = list(window.document.cards)
    window.document.set_card_color_slot(card_ids[0], "slot_white")
    window.document.set_card_color_slot(card_ids[1], "slot_yellow")
    for card_id in card_ids[:2]:
        window.canvas_scene.item_for_card(card_id).setSelected(True)

    window._rebuild_card_color_menu()

    assert not any(action.isChecked() for action in window.card_color_menu.actions())


def test_selecting_a_card_color_applies_to_the_whole_selection(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)
    card_ids = list(window.document.cards)
    original_slots = {cid: window.document.get_card(cid).color_slot for cid in card_ids}
    for card_id in card_ids:
        window.canvas_scene.item_for_card(card_id).setSelected(True)

    window._on_change_card_color("slot_blue")

    for card_id in card_ids:
        assert window.document.get_card(card_id).color_slot == "slot_blue"
    assert window.undo_stack.canUndo()

    window.undo_stack.undo()
    # Each card's own original color is restored, not a shared value --
    # matters here specifically because one fixture card already starts
    # as "slot_blue", so a blanket "!= slot_blue" check would be wrong.
    for card_id in card_ids:
        assert window.document.get_card(card_id).color_slot == original_slots[card_id]


def test_selecting_the_same_card_color_does_not_push_a_command(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)
    card_id = next(iter(window.document.cards))
    window.document.set_card_color_slot(card_id, "slot_white")
    window.canvas_scene.item_for_card(card_id).setSelected(True)

    window._on_change_card_color("slot_white")

    assert window.undo_stack.canUndo() is False


def test_add_to_stack_existing_stack_action_adds_selection(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)
    window.document.add_stack(Stack(id="s_1", label="Chapter 1"))
    card_id = next(iter(window.document.cards))
    window.canvas_scene.item_for_card(card_id).setSelected(True)

    window._on_add_to_existing_stack("s_1")

    assert window.document.get_card(card_id).stack_id == "s_1"
    assert card_id in window.document.get_stack("s_1").card_ids


def test_add_to_stack_actions_are_noop_with_no_canvas_selection(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)

    window._on_add_to_new_stack()  # must not raise
    window._on_add_to_existing_stack("s_missing")  # must not raise


def test_remove_from_stack_action_disabled_when_overlay_closed(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window._set_document(_document_with_stack(), path=None)

    window._update_remove_from_stack_action()

    assert not window.remove_from_stack_action.isEnabled()


def test_remove_from_stack_action_enabled_when_overlay_open_with_focused_tile(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window._set_document(_document_with_stack(), path=None)
    window.canvas_view.resize(800, 600)
    window.canvas_view.stack_overlay.open("s_1", window.document, window.undo_stack)

    window._update_remove_from_stack_action()

    assert window.remove_from_stack_action.isEnabled()


def test_on_remove_from_stack_ejects_the_focused_tile(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window._set_document(_document_with_stack(), path=None)
    window.canvas_view.resize(800, 600)
    window.canvas_view.stack_overlay.open("s_1", window.document, window.undo_stack)
    window.canvas_view.stack_overlay._focus_tile("c_1")

    window._on_remove_from_stack()

    qtbot.waitUntil(lambda: window.undo_stack.count() == 1)
    assert window.document.get_card("c_1").stack_id is None


def test_view_extents_action_disabled_while_stack_overlay_open(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window._set_document(_document_with_stack(), path=None)
    window.canvas_view.resize(800, 600)
    assert window.view_extents_action.isEnabled()

    # Enabled state changes purely via the openedChanged signal fired from
    # inside open()/dismiss() -- no manual refresh call here -- matching
    # the same live-enablement pattern already used for Cut/Copy/Paste.
    window.canvas_view.stack_overlay.open("s_1", window.document, window.undo_stack)
    assert not window.view_extents_action.isEnabled()

    window.canvas_view.stack_overlay.dismiss()
    assert window.view_extents_action.isEnabled()


def test_open_file_with_zoom_extents_setting_fits_small_content_natively(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitActive(window)
    assert window._settings.view_on_open == "zoom_extents"  # the default

    window.open_file(FIXTURE_PATH)  # sample.idxcards comfortably fits at 1:1

    qtbot.waitUntil(lambda: window.canvas_view.zoom == 1.0)


def test_open_file_with_last_save_setting_restores_saved_view(qtbot, tmp_path):
    document = load_document(FIXTURE_PATH)
    document.view_zoom = 0.6
    document.view_center_x = 300.0
    document.view_center_y = 400.0
    path = tmp_path / "with_view.idxcards"
    save_document(document, path)

    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitActive(window)
    window._settings.view_on_open = "last_save"

    window.open_file(path)

    qtbot.waitUntil(lambda: window.canvas_view.zoom == 0.6)
    center = window.canvas_view.mapToScene(window.canvas_view.viewport().rect().center())
    assert abs(center.x() - 300.0) < 2.0
    assert abs(center.y() - 400.0) < 2.0


def test_open_file_with_last_save_setting_falls_back_without_saved_view(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitActive(window)
    window._settings.view_on_open = "last_save"

    window.open_file(FIXTURE_PATH)  # predates this feature -- no saved view state

    qtbot.waitUntil(lambda: window.canvas_view.zoom == 1.0)


def test_save_to_captures_live_view_state_onto_document(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitActive(window)
    window.open_file(FIXTURE_PATH)
    qtbot.waitUntil(lambda: window.canvas_view.zoom == 1.0)  # drain the deferred initial view
    window.canvas_view.restore_view_state(0.75, 300.0, 400.0)

    path = tmp_path / "saved.idxcards"
    window._save_to(path)

    reloaded = load_document(path)
    assert reloaded.view_zoom == 0.75
    assert abs(reloaded.view_center_x - 300.0) < 2.0
    assert abs(reloaded.view_center_y - 400.0) < 2.0
