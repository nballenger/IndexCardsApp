from pathlib import Path

from PySide6.QtGui import QAction, QCloseEvent, QColor, QKeySequence, QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QColorDialog,
    QDialog,
    QFileDialog,
    QGraphicsSimpleTextItem,
    QMessageBox,
)

from indexcards.app_settings import AppSettings
from indexcards.canvas.link_item import LinkItem
from indexcards.list_view.card_table_model import COLUMN_COLOR, COLUMN_TAGS, COLUMN_TEXT
from indexcards.main_window import MainWindow
from indexcards.models.card import Card
from indexcards.models.document import Document
from indexcards.models.link import Link
from indexcards.persistence.file_io import load_document, save_document
from indexcards.widgets.arrange_dialog import ArrangeDialog
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


def test_link_mode_action_toggles_controller(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.canvas_view.link_controller.active is False
    window.link_mode_action.setChecked(True)
    assert window.canvas_view.link_controller.active is True
    window.link_mode_action.setChecked(False)
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


def test_auto_arrange_by_color_groups_and_undo_restores_layout(qtbot, monkeypatch):
    monkeypatch.setattr(ArrangeDialog, "exec", lambda self: QDialog.DialogCode.Accepted)

    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Arrange Test")
    document.add_card(Card(id="c_1", color="#AAAAAA", x=1.0, y=2.0))
    document.add_card(Card(id="c_2", color="#AAAAAA", x=3.0, y=4.0))
    document.add_card(Card(id="c_3", color="#BBBBBB", x=5.0, y=6.0))
    window._set_document(document, path=None)
    original_positions = {card.id: (card.x, card.y) for card in document.iter_cards()}

    window._on_auto_arrange()

    # c_1 and c_2 share a color/stack, so they land much closer together
    # (a small diagonal cascade) than c_3, which is a full stack away.
    same_stack_gap = document.get_card("c_2").x - document.get_card("c_1").x
    different_stack_gap = document.get_card("c_3").x - document.get_card("c_1").x
    assert 0 < same_stack_gap < different_stack_gap
    assert window.undo_stack.canUndo()

    window.undo_stack.undo()
    for card_id, pos in original_positions.items():
        assert (document.get_card(card_id).x, document.get_card(card_id).y) == pos


def test_auto_arrange_by_tag_shows_stack_labels(qtbot, monkeypatch):
    monkeypatch.setattr("indexcards.widgets.arrange_dialog.TAGS_ENABLED", True)

    def fake_exec(self):
        self.tag_radio.setChecked(True)
        self.tag_combo.setCurrentText("plot")
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(ArrangeDialog, "exec", fake_exec)

    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Arrange Test")
    document.add_card(Card(id="c_1", tags=["plot"], x=1.0, y=2.0))
    document.add_card(Card(id="c_2", tags=[], x=3.0, y=4.0))
    window._set_document(document, path=None)

    window._on_auto_arrange()

    labels = [
        item for item in window.canvas_scene.items() if isinstance(item, QGraphicsSimpleTextItem)
    ]
    assert len(labels) == 2


def test_auto_arrange_by_color_does_not_show_stack_labels(qtbot, monkeypatch):
    monkeypatch.setattr(ArrangeDialog, "exec", lambda self: QDialog.DialogCode.Accepted)

    window = MainWindow()
    qtbot.addWidget(window)
    document = Document(name="Arrange Test")
    document.add_card(Card(id="c_1", color="#AAAAAA", x=1.0, y=2.0))
    document.add_card(Card(id="c_2", color="#BBBBBB", x=3.0, y=4.0))
    window._set_document(document, path=None)

    window._on_auto_arrange()  # defaults to color mode

    labels = [
        item for item in window.canvas_scene.items() if isinstance(item, QGraphicsSimpleTextItem)
    ]
    assert labels == []


def test_auto_arrange_cancelled_dialog_does_nothing(qtbot, monkeypatch):
    monkeypatch.setattr(ArrangeDialog, "exec", lambda self: QDialog.DialogCode.Rejected)

    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)
    original_positions = {
        card.id: (card.x, card.y) for card in window.document.iter_cards()
    }

    window._on_auto_arrange()

    assert window.undo_stack.canUndo() is False
    for card_id, pos in original_positions.items():
        card = window.document.get_card(card_id)
        assert (card.x, card.y) == pos


def test_auto_arrange_save_reload_preserves_new_layout(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(ArrangeDialog, "exec", lambda self: QDialog.DialogCode.Accepted)

    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)

    window._on_auto_arrange()
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
