from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import QAbstractItemView, QPlainTextEdit

from indexcards.app_settings import AppSettings
from indexcards.list_view.card_table_model import (
    COLUMN_COLOR,
    COLUMN_ID,
    COLUMN_LINKS,
    COLUMN_TAGS,
    COLUMN_TEXT,
    CardTableModel,
)
from indexcards.list_view.list_view_widget import (
    _EMPTY_DOCUMENT_TEXT,
    _EMPTY_SEARCH_TEXT,
    _MIN_COLUMN_WIDTH,
    ListViewWidget,
)
from indexcards.models.card import Card
from indexcards.models.document import Document
from indexcards.models.stack import Stack


def _visible_card_ids(widget: ListViewWidget) -> list[str]:
    ids = []
    for row in range(widget.proxy_model.rowCount()):
        source_row = widget.proxy_model.mapToSource(widget.proxy_model.index(row, 0)).row()
        ids.append(widget.model.card_id_at_row(source_row))
    return ids


def test_tags_column_hidden_by_default(qtbot):
    document = Document(name="Test")
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)

    widget.set_model(model)

    assert widget.table_view.isColumnHidden(COLUMN_TAGS) is True


def test_tags_column_visible_when_tags_enabled(qtbot, monkeypatch):
    monkeypatch.setattr("indexcards.list_view.list_view_widget.TAGS_ENABLED", True)
    document = Document(name="Test")
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)

    widget.set_model(model)

    assert widget.table_view.isColumnHidden(COLUMN_TAGS) is False


def test_empty_label_visible_for_empty_document(qtbot):
    document = Document(name="Test")
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)
    widget.show()

    widget.set_model(model)

    assert widget.empty_label.isVisible() is True


def test_empty_label_hidden_once_document_has_cards(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="something"))
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)
    widget.show()

    widget.set_model(model)

    assert widget.empty_label.isVisible() is False


def test_empty_label_reappears_after_deleting_the_last_card(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="something"))
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.set_model(model)
    assert widget.empty_label.isVisible() is False

    model.remove_cards_at_rows([0])

    assert widget.empty_label.isVisible() is True


def test_empty_label_visible_when_search_filters_out_everything(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="apple"))
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.set_model(model)
    assert widget.empty_label.isVisible() is False

    widget.set_search_query("nonexistent query")
    assert widget.empty_label.isVisible() is True

    widget.set_search_query("")
    assert widget.empty_label.isVisible() is False


def test_add_card_emits_card_created_signal(qtbot):
    document = Document(name="Test")
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)
    widget.set_model(model)

    received = []
    widget.cardCreated.connect(received.append)

    widget._add_card()

    assert len(received) == 1
    assert received[0] in document.cards


def test_enter_on_last_row_creates_new_card(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="first"))
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)
    widget.set_model(model)
    widget.table_view.setCurrentIndex(widget.proxy_model.index(0, 0))

    qtbot.keyClick(widget.table_view, Qt.Key.Key_Return)

    assert model.rowCount() == 2


def test_enter_on_last_row_opens_inline_text_editing_not_dock(qtbot):
    # Unlike the toolbar/context-menu Add Card (which focuses the dock),
    # Enter-on-last-row is a spreadsheet-style flow: it should open inline
    # editing on the new row's Text cell and NOT emit cardCreated (which is
    # what drives the dock-focus behavior in MainWindow).
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="first"))
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.set_model(model)
    widget.table_view.setCurrentIndex(widget.proxy_model.index(0, 0))

    received = []
    widget.cardCreated.connect(received.append)
    qtbot.keyClick(widget.table_view, Qt.Key.Key_Return)

    assert received == []
    assert widget.table_view.state() == QAbstractItemView.State.EditingState
    assert widget.table_view.currentIndex().column() == COLUMN_TEXT
    assert widget.table_view.currentIndex().row() == widget.proxy_model.rowCount() - 1


def test_enter_on_non_last_row_does_not_create_card(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="first"))
    document.add_card(Card(id="c_2", text="second"))
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)
    widget.set_model(model)
    widget.table_view.setCurrentIndex(widget.proxy_model.index(0, 0))

    qtbot.keyClick(widget.table_view, Qt.Key.Key_Return)

    assert model.rowCount() == 2


def test_enter_while_editing_does_not_also_create_card(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="first"))
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.set_model(model)
    index = widget.proxy_model.index(0, 0)
    widget.table_view.setCurrentIndex(index)
    widget.table_view.edit(index)

    qtbot.keyClick(widget.table_view, Qt.Key.Key_Return)

    assert model.rowCount() == 1


def test_enter_with_no_model_does_not_crash(qtbot):
    widget = ListViewWidget()
    qtbot.addWidget(widget)

    qtbot.keyClick(widget.table_view, Qt.Key.Key_Return)  # must not raise


def test_shift_enter_inserts_newline_plain_enter_commits(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="first"))
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.set_model(model)
    index = widget.proxy_model.index(0, COLUMN_TEXT)
    widget.table_view.edit(index)

    editor = widget.table_view.viewport().findChild(QPlainTextEdit)
    assert editor is not None

    qtbot.keyClick(editor, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    qtbot.keyClicks(editor, "second line")
    qtbot.keyClick(editor, Qt.Key.Key_Return)

    assert document.get_card("c_1").text == "first\nsecond line"
    assert widget.table_view.state() != QAbstractItemView.State.EditingState


def test_single_click_on_color_cell_opens_editor(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="first", color_slot="slot_yellow"))
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.set_model(model)

    color_index = widget.proxy_model.index(0, COLUMN_COLOR)
    widget._on_cell_clicked(color_index)

    assert widget.table_view.state() == QAbstractItemView.State.EditingState


def test_single_click_on_text_cell_does_not_open_editor(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="first"))
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.set_model(model)

    text_index = widget.proxy_model.index(0, COLUMN_TEXT)
    widget._on_cell_clicked(text_index)

    assert widget.table_view.state() != QAbstractItemView.State.EditingState


def test_add_and_delete_buttons_removed(qtbot):
    widget = ListViewWidget()
    qtbot.addWidget(widget)

    assert not hasattr(widget, "add_button")
    assert not hasattr(widget, "delete_button")


def test_double_click_on_empty_background_creates_and_edits_card(qtbot):
    document = Document(name="Test")
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.set_model(model)

    qtbot.mouseDClick(widget.table_view.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(50, 50))

    assert model.rowCount() == 1
    assert widget.table_view.state() == QAbstractItemView.State.EditingState
    assert widget.table_view.currentIndex().column() == COLUMN_TEXT


def test_double_click_below_last_row_creates_card(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="first"))
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.set_model(model)

    # Well below the single existing row, where indexAt() is invalid.
    qtbot.mouseDClick(widget.table_view.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(50, 300))

    assert model.rowCount() == 2


def test_double_click_on_existing_row_does_not_create_card(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="first"))
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.set_model(model)

    index = widget.proxy_model.index(0, COLUMN_TEXT)
    rect = widget.table_view.visualRect(index)
    qtbot.mouseDClick(widget.table_view.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())

    assert model.rowCount() == 1


def test_double_click_with_no_model_does_not_crash(qtbot):
    widget = ListViewWidget()
    qtbot.addWidget(widget)
    widget.show()

    qtbot.mouseDClick(widget.table_view.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(50, 50))


def test_color_column_visually_before_text_before_links(qtbot):
    document = Document(name="Test")
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)
    widget.set_model(model)

    header = widget.table_view.horizontalHeader()
    assert header.visualIndex(COLUMN_COLOR) < header.visualIndex(COLUMN_TEXT)
    assert header.visualIndex(COLUMN_TEXT) < header.visualIndex(COLUMN_LINKS)


def test_id_column_is_leftmost(qtbot):
    document = Document(name="Test")
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)
    widget.set_model(model)

    header = widget.table_view.horizontalHeader()
    assert header.visualIndex(COLUMN_ID) == 0


def test_initial_column_widths_roughly_match_requested_fractions(qtbot):
    document = Document(name="Test")
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)
    widget.resize(1000, 400)
    widget.show()
    widget.set_model(model)
    qtbot.waitExposed(widget)

    viewport_width = widget.table_view.viewport().width()
    color_width = widget.table_view.columnWidth(COLUMN_COLOR)
    text_width = widget.table_view.columnWidth(COLUMN_TEXT)

    assert abs(color_width - viewport_width * 0.10) < 20
    assert abs(text_width - viewport_width * 0.70) < 20


def test_column_widths_apply_correctly_when_model_set_before_widget_is_sized(qtbot):
    # Regression: MainWindow calls set_model() during its own __init__,
    # before the window (and this widget) has ever been shown — at that
    # point the viewport is still some small pre-layout default width.
    # The initial split must not lock in against that; it should wait for
    # a later, real resize once the widget is actually shown.
    document = Document(name="Test")
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)

    widget.set_model(model)  # model attached first, widget still tiny/unshown

    widget.resize(1000, 400)
    widget.show()
    qtbot.waitExposed(widget)

    viewport_width = widget.table_view.viewport().width()
    text_width = widget.table_view.columnWidth(COLUMN_TEXT)
    assert abs(text_width - viewport_width * 0.70) < 20


def test_minimum_column_width_enforced_when_narrow(qtbot):
    document = Document(name="Test")
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)
    widget.resize(150, 400)  # narrow enough that 10% of it is under the minimum
    widget.show()
    widget.set_model(model)
    qtbot.waitExposed(widget)

    assert widget.table_view.columnWidth(COLUMN_COLOR) >= _MIN_COLUMN_WIDTH


def test_columns_freely_resizable_after_initial_split(qtbot):
    document = Document(name="Test")
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)
    widget.resize(1000, 400)
    widget.show()
    widget.set_model(model)
    qtbot.waitExposed(widget)

    widget.table_view.setColumnWidth(COLUMN_TEXT, 555)

    assert widget.table_view.columnWidth(COLUMN_TEXT) == 555


def test_sorting_text_column_orders_alphabetically(qtbot):
    # sortByColumn() is the same call QHeaderView's own click-to-sort
    # handling makes internally, so this exercises exactly what a real
    # header click does — SortableColumnsHeaderView's own click-blocking
    # for non-sortable columns is covered separately, at the unit level,
    # in test_sortable_header_view.py (synthetic mouse events don't
    # reliably reach a bare QHeaderView under the offscreen test platform).
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="banana"))
    document.add_card(Card(id="c_2", text="apple"))
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.set_model(model)

    widget.table_view.sortByColumn(COLUMN_TEXT, Qt.SortOrder.AscendingOrder)

    assert _visible_card_ids(widget) == ["c_2", "c_1"]


def test_sorting_color_column_orders_by_theme_slot_order(qtbot):
    document = Document(name="Test")
    # Gray is last in the theme's slot order, White is first.
    document.add_card(Card(id="c_1", text="a", color_slot="slot_gray"))
    document.add_card(Card(id="c_2", text="b", color_slot="slot_white"))
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.set_model(model)

    widget.table_view.sortByColumn(COLUMN_COLOR, Qt.SortOrder.AscendingOrder)

    assert _visible_card_ids(widget) == ["c_2", "c_1"]


def test_empty_document_shows_double_click_hint(qtbot):
    document = Document(name="Test")
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.set_model(model)

    assert widget.empty_label.text() == _EMPTY_DOCUMENT_TEXT


def test_search_filtered_to_empty_shows_search_hint(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="apple"))
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.set_model(model)

    widget.set_search_query("nonexistent")

    assert widget.empty_label.text() == _EMPTY_SEARCH_TEXT


def test_deleting_last_card_while_search_filters_everything_shows_document_hint(qtbot):
    # Regression: with a non-matching search already active, the proxy's
    # visible row count is 0 both before and after the card is deleted —
    # no proxy row-change signal fires — so the label must also listen to
    # the *source* model's own signals, or it's left showing stale
    # "No cards match the current search" text after the document is
    # actually empty.
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="apple"))
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.set_model(model)
    widget.set_search_query("nonexistent")
    assert widget.empty_label.text() == _EMPTY_SEARCH_TEXT

    model.remove_cards_at_rows([0])

    assert widget.empty_label.text() == _EMPTY_DOCUMENT_TEXT


def test_list_view_widget_uses_passed_in_settings(qtbot):
    settings = AppSettings()
    widget = ListViewWidget(settings=settings)
    qtbot.addWidget(widget)

    assert widget._settings is settings


def test_list_view_widget_defaults_to_in_memory_settings(qtbot):
    widget = ListViewWidget()
    qtbot.addWidget(widget)

    assert isinstance(widget._settings, AppSettings)


def test_stack_tab_bar_hidden_with_no_stacks(qtbot):
    document = Document(name="Test")
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)
    widget.show()

    widget.set_model(model)

    assert widget.stack_tab_bar.isVisible() is False
    assert widget.stack_tab_bar.count() == 1  # "On Canvas" tab always exists, just hidden


def test_stack_tab_bar_shown_with_one_stack(qtbot):
    document = Document(name="Test")
    document.add_stack(Stack(id="s_1", label="Chapter 1"))
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)
    widget.show()

    widget.set_model(model)

    assert widget.stack_tab_bar.isVisible() is True
    assert widget.stack_tab_bar.count() == 2
    assert widget.stack_tab_bar.tabText(0) == "On Canvas"
    assert widget.stack_tab_bar.tabText(1) == "Chapter 1"


def test_stack_tab_bar_unlabeled_stack_shows_placeholder_title(qtbot):
    document = Document(name="Test")
    document.add_stack(Stack(id="s_1"))
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)

    widget.set_model(model)

    assert widget.stack_tab_bar.tabText(1) == "(unlabeled)"


def test_stack_tab_bar_updates_live_on_stack_added(qtbot):
    document = Document(name="Test")
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.set_model(model)

    document.add_stack(Stack(id="s_1", label="Chapter 1"))

    assert widget.stack_tab_bar.isVisible() is True
    assert widget.stack_tab_bar.tabText(1) == "Chapter 1"


def test_stack_tab_bar_hides_again_when_last_stack_removed(qtbot):
    document = Document(name="Test")
    document.add_stack(Stack(id="s_1"))
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.set_model(model)

    document.remove_stack("s_1")

    assert widget.stack_tab_bar.isVisible() is False


def test_stack_tab_bar_updates_title_on_label_change(qtbot):
    document = Document(name="Test")
    document.add_stack(Stack(id="s_1", label="Old Name"))
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)
    widget.set_model(model)

    document.set_stack_label("s_1", "New Name")

    assert widget.stack_tab_bar.tabText(1) == "New Name"


def test_on_canvas_tab_shows_only_unstacked_cards(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="loose"))
    document.add_card(Card(id="c_2", text="stacked", stack_id="s_1"))
    document.add_stack(Stack(id="s_1", label="Chapter 1", card_ids=["c_2"]))
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)

    widget.set_model(model)

    assert _visible_card_ids(widget) == ["c_1"]


def test_clicking_stack_tab_shows_its_cards(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="loose"))
    document.add_card(Card(id="c_2", text="stacked", stack_id="s_1"))
    document.add_stack(Stack(id="s_1", label="Chapter 1", card_ids=["c_2"]))
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)
    widget.set_model(model)

    widget.stack_tab_bar.setCurrentIndex(1)

    assert _visible_card_ids(widget) == ["c_2"]


def test_switching_back_to_on_canvas_tab_restores_unstacked_cards(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="loose"))
    document.add_card(Card(id="c_2", text="stacked", stack_id="s_1"))
    document.add_stack(Stack(id="s_1", card_ids=["c_2"]))
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)
    widget.set_model(model)
    widget.stack_tab_bar.setCurrentIndex(1)

    widget.stack_tab_bar.setCurrentIndex(0)

    assert _visible_card_ids(widget) == ["c_1"]


def test_removing_active_stack_tab_falls_back_to_on_canvas(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="loose"))
    document.add_card(Card(id="c_2", text="stacked", stack_id="s_1"))
    document.add_stack(Stack(id="s_1", card_ids=["c_2"]))
    model = CardTableModel(document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)
    widget.set_model(model)
    widget.stack_tab_bar.setCurrentIndex(1)

    document.remove_cards_from_stack("s_1", ["c_2"])
    document.remove_stack("s_1")

    assert widget.stack_tab_bar.currentIndex() == 0
    assert _visible_card_ids(widget) == ["c_1", "c_2"]


def test_set_model_on_new_document_resets_stack_tabs(qtbot):
    old_document = Document(name="Old")
    old_document.add_stack(Stack(id="s_1", label="Old Stack"))
    old_model = CardTableModel(old_document, undo_stack=QUndoStack())
    widget = ListViewWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.set_model(old_model)
    assert widget.stack_tab_bar.count() == 2

    new_document = Document(name="New")
    new_model = CardTableModel(new_document, undo_stack=QUndoStack())
    widget.set_model(new_model)

    assert widget.stack_tab_bar.count() == 1
    assert widget.stack_tab_bar.isVisible() is False
