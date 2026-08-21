from pathlib import Path

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QMessageBox

from indexcards.canvas.link_item import LinkItem
from indexcards.list_view.card_table_model import COLUMN_COLOR, COLUMN_TAGS, COLUMN_TEXT
from indexcards.main_window import MainWindow
from indexcards.persistence.file_io import load_document

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
    assert len(window.canvas_scene.items()) == 4  # 3 cards + 1 link from the fixture
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


def test_list_selection_loads_markdown_editor(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)

    index = window.card_table_model.index(0, COLUMN_TEXT)
    window.list_view.table_view.setCurrentIndex(index)

    assert window.markdown_editor.text_edit.isEnabled()
    assert "Working title" in window.markdown_editor.text_edit.toPlainText()


def test_canvas_selection_loads_markdown_editor(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)

    item = window.canvas_scene.item_for_card("c_7bd310aa")
    item.setSelected(True)

    assert window.markdown_editor.text_edit.isEnabled()
    assert "Card two" in window.markdown_editor.text_edit.toPlainText()


def test_editing_via_dock_updates_list_view_and_undo_works(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)

    index = window.card_table_model.index(0, COLUMN_TEXT)
    window.list_view.table_view.setCurrentIndex(index)

    cursor = window.markdown_editor.text_edit.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    cursor.insertText("Edited via dock")
    window.markdown_editor._commit()

    assert "Edited via dock" in window.card_table_model.index(0, COLUMN_TEXT).data()
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
    assert "Untagged loose thought" in window.markdown_editor.text_edit.toPlainText()


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
    assert "Card two" in window.markdown_editor.text_edit.toPlainText()


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
    assert "Card two" in window.markdown_editor.text_edit.toPlainText()


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
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    )
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
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.No)
    )
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)

    window.canvas_scene.item_for_card("c_4f9a1b2c").setSelected(True)

    window._on_canvas_delete_requested()

    assert "c_4f9a1b2c" in window.document.cards
    assert window.undo_stack.canUndo() is False


def test_canvas_delete_card_plus_its_own_incident_link_does_not_double_delete(qtbot, monkeypatch):
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    )
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
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(
            lambda parent, title, message, *a, **k: seen_messages.append(message)
            or QMessageBox.StandardButton.Yes
        ),
    )
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
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.No)
    )
    window = MainWindow()
    qtbot.addWidget(window)
    window.open_file(FIXTURE_PATH)

    row = window.card_table_model.row_for_card_id("c_4f9a1b2c")
    window.list_view.table_view.selectRow(row)
    window.list_view._delete_selected_cards()

    assert "c_4f9a1b2c" in window.document.cards
