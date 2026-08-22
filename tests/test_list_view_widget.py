from PySide6.QtCore import Qt
from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import QAbstractItemView, QPlainTextEdit

from indexcards.list_view.card_table_model import COLUMN_COLOR, COLUMN_TEXT, CardTableModel
from indexcards.list_view.list_view_widget import ListViewWidget
from indexcards.models.card import Card
from indexcards.models.document import Document


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
    document.add_card(Card(id="c_1", text="first", color="#F6E27A"))
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
