from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QAction, QCloseEvent, QColor, QKeyEvent, QKeySequence, QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QColorDialog,
    QDialog,
    QFileDialog,
    QMessageBox,
)

from indexcards.app_settings import AppSettings
from indexcards.canvas.canvas_view import VIEW_EXTENTS_MARGIN
from indexcards.canvas.link_item import LinkItem
from indexcards.list_view.card_table_model import COLUMN_COLOR, COLUMN_TAGS, COLUMN_TEXT
from indexcards.main_window import MainWindow
from indexcards.models.card import Card
from indexcards.models.document import Document
from indexcards.models.link import Link
from indexcards.models.stack import Stack
from indexcards.persistence.file_io import load_document, save_document
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

    assert window.windowTitle() == "Index Cards — Sample Fixture"
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
    assert window.windowTitle() == "Index Cards — Sample Fixture*"

    window.undo_stack.undo()

    assert window.undo_stack.isClean() is True
    assert window.windowTitle() == "Index Cards — Sample Fixture"


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
    assert window.windowTitle() == "Index Cards — Sample Fixture"

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


def test_main_window_has_arrange_menu_to_the_right_of_view(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    menu_titles = [action.text() for action in window.menuBar().actions()]
    assert menu_titles.index("&Arrange") == menu_titles.index("&View") + 1


def test_arrange_menu_has_tile_scatter_and_columns_submenu(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    arrange_menu = next(
        action.menu() for action in window.menuBar().actions() if action.text() == "&Arrange"
    )
    action_texts = [action.text() for action in arrange_menu.actions()]
    assert action_texts == ["Tile", "Scatter", "Columns", "", "Gather Stacks"]
    assert window.arrange_tile_action in arrange_menu.actions()
    assert window.arrange_scatter_action in arrange_menu.actions()
    assert window.arrange_columns_menu.menuAction() in arrange_menu.actions()
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


def test_auto_arrange_columns_by_color_groups_and_undo_restores_layout(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Arrange Test")
    document.add_card(Card(id="c_1", color="#A8D8F0", x=1.0, y=2.0))  # Blue
    document.add_card(Card(id="c_2", color="#A8D8F0", x=3.0, y=4.0))  # Blue
    document.add_card(Card(id="c_3", color="#B7E4C7", x=5.0, y=6.0))  # Green
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

    def fake_arrange_avoiding_pinned(
        cards, group_by, tag=None, aspect_ratio=1.0, overflow_limit=None
    ):
        captured["aspect_ratio"] = aspect_ratio
        return {card.id: (card.x, card.y) for card in cards}

    monkeypatch.setattr(
        "indexcards.main_window.arrange_avoiding_pinned", fake_arrange_avoiding_pinned
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
    document.add_card(Card(id="c_1", color="#AAAAAA", x=1.0, y=2.0))
    document.add_card(Card(id="c_2", color="#AAAAAA", x=3.0, y=4.0))
    document.add_card(Card(id="c_3", color="#BBBBBB", x=5.0, y=6.0))
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
    colors = ["#AAAAAA", "#BBBBBB", "#CCCCCC", "#DDDDDD", "#EEEEEE", "#111111"]
    for i, color in enumerate(colors):
        document.add_card(Card(id=f"c_{i}", color=color, x=float(i), y=float(i)))
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
    document.add_card(Card(id="c_1", color="#AAAAAA", x=1.0, y=2.0))
    document.add_card(Card(id="c_2", color="#AAAAAA", x=3.0, y=4.0))
    document.add_card(Card(id="c_3", color="#BBBBBB", x=5.0, y=6.0))
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
    assert window.document.name == "Sample Fixture"
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
    assert new_window.document.name == "Sample Fixture"
    assert window.document.name == "Other"  # original window untouched


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


def test_new_document_uses_settings_default_background_color(qtbot):
    manager = WindowManager(settings=AppSettings())
    manager.settings.default_background_color = "#abcdef"

    window = manager.open_new_window()
    qtbot.addWidget(window)

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
    assert window.tabs.currentWidget() is window.canvas_view

    window._on_create_card_shortcut()

    assert window.card_table_model.rowCount() == 1
    card_id = window.card_table_model.card_id_at_row(0)
    item = window.canvas_scene.item_for_card(card_id)
    qtbot.waitUntil(lambda: item._editing)


def test_list_view_card_created_edits_text_cell_on_list_tab(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitActive(window)
    window.tabs.setCurrentWidget(window.list_view)

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
    window.tabs.setCurrentWidget(window.list_view)

    window.view_canvas_action.trigger()

    assert window.tabs.currentWidget() is window.canvas_view


def test_view_list_action_switches_to_list_tab(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.tabs.currentWidget() is window.canvas_view

    window.view_list_action.trigger()

    assert window.tabs.currentWidget() is window.list_view


def test_switching_tabs_updates_view_menu_checked_state(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.view_canvas_action.isChecked()
    assert not window.view_list_action.isChecked()

    window.tabs.setCurrentWidget(window.list_view)

    assert window.view_list_action.isChecked()
    assert not window.view_canvas_action.isChecked()


def test_select_all_on_canvas_tab_selects_all_cards(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)
    window.tabs.setCurrentWidget(window.canvas_view)

    window._on_select_all()

    assert set(window.canvas_scene.selected_card_ids()) == set(window.document.cards.keys())


def test_select_all_on_list_tab_selects_all_rows(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)
    window.tabs.setCurrentWidget(window.list_view)

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
    window.tabs.setCurrentWidget(window.list_view)
    window.canvas_scene.item_for_card(card_ids[0]).setSelected(True)

    window._on_select_linked()

    assert window.tabs.currentWidget() is window.canvas_view
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
