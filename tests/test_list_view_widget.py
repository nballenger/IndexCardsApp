from PySide6.QtGui import QUndoStack

from indexcards.list_view.card_table_model import CardTableModel
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
