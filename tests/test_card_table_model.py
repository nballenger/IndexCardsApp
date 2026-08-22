from PySide6.QtCore import Qt
from PySide6.QtGui import QUndoStack

from indexcards.list_view.card_table_model import (
    COLUMN_COLOR,
    COLUMN_ID,
    COLUMN_LINKS,
    COLUMN_TAGS,
    COLUMN_TEXT,
    CardTableModel,
)
from indexcards.models.card import Card
from indexcards.models.document import Document
from indexcards.models.link import Link


def _document_with_cards() -> Document:
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="first", color="#F6E27A", tags=["a", "b"]))
    document.add_card(Card(id="c_2", text="second", color="#A8D8F0", tags=[]))
    return document


def test_row_and_column_counts():
    model = CardTableModel(_document_with_cards())
    assert model.rowCount() == 2
    assert model.columnCount() == 5


def test_data_returns_text_color_and_joined_tags():
    model = CardTableModel(_document_with_cards())

    assert model.index(0, COLUMN_TEXT).data() == "first"
    assert model.index(0, COLUMN_COLOR).data() == "#F6E27A"
    assert model.index(0, COLUMN_TAGS).data() == "a, b"
    assert model.index(1, COLUMN_TAGS).data() == ""


def test_id_column_shows_card_id():
    model = CardTableModel(_document_with_cards())

    assert model.index(0, COLUMN_ID).data() == "c_1"
    assert model.index(1, COLUMN_ID).data() == "c_2"


def test_id_column_is_never_editable_even_with_undo_stack():
    document = _document_with_cards()
    stack = QUndoStack()
    model = CardTableModel(document, undo_stack=stack)

    index = model.index(0, COLUMN_ID)
    assert not (model.flags(index) & Qt.ItemFlag.ItemIsEditable)
    assert model.setData(index, "ignored") is False


def test_card_id_at_row_matches_insertion_order():
    model = CardTableModel(_document_with_cards())
    assert model.card_id_at_row(0) == "c_1"
    assert model.card_id_at_row(1) == "c_2"


def test_model_reflects_card_added_after_construction(qtbot):
    document = _document_with_cards()
    model = CardTableModel(document)

    with qtbot.waitSignal(model.rowsInserted, timeout=1000):
        document.add_card(Card(id="c_3", text="third"))

    assert model.rowCount() == 3
    assert model.card_id_at_row(2) == "c_3"


def test_model_reflects_card_removed(qtbot):
    document = _document_with_cards()
    model = CardTableModel(document)

    with qtbot.waitSignal(model.rowsRemoved, timeout=1000):
        document.remove_card("c_1")

    assert model.rowCount() == 1
    assert model.card_id_at_row(0) == "c_2"


def test_model_reflects_card_text_change(qtbot):
    document = _document_with_cards()
    model = CardTableModel(document)

    with qtbot.waitSignal(model.dataChanged, timeout=1000):
        document.set_card_text("c_1", "updated")

    assert model.index(0, COLUMN_TEXT).data() == "updated"


def test_without_undo_stack_model_is_read_only():
    model = CardTableModel(_document_with_cards())
    index = model.index(0, COLUMN_TEXT)

    assert not (model.flags(index) & Qt.ItemFlag.ItemIsEditable)
    assert model.setData(index, "new text") is False


def test_set_data_on_text_column_pushes_undo_command():
    document = _document_with_cards()
    stack = QUndoStack()
    model = CardTableModel(document, undo_stack=stack)
    index = model.index(0, COLUMN_TEXT)

    assert model.flags(index) & Qt.ItemFlag.ItemIsEditable
    assert model.setData(index, "edited") is True
    assert document.get_card("c_1").text == "edited"
    assert stack.canUndo()

    stack.undo()
    assert document.get_card("c_1").text == "first"


def test_set_data_on_color_column_pushes_undo_command():
    document = _document_with_cards()
    stack = QUndoStack()
    model = CardTableModel(document, undo_stack=stack)
    index = model.index(0, COLUMN_COLOR)

    assert model.setData(index, "#A8D8F0") is True
    assert document.get_card("c_1").color == "#A8D8F0"

    stack.undo()
    assert document.get_card("c_1").color == "#F6E27A"


def test_set_data_on_tags_column_pushes_undo_command():
    document = _document_with_cards()
    stack = QUndoStack()
    model = CardTableModel(document, undo_stack=stack)
    index = model.index(0, COLUMN_TAGS)

    assert model.setData(index, ["x", "y"]) is True
    assert document.get_card("c_1").tags == ["x", "y"]

    stack.undo()
    assert document.get_card("c_1").tags == ["a", "b"]


def test_set_data_with_unchanged_value_does_not_push_command():
    document = _document_with_cards()
    stack = QUndoStack()
    model = CardTableModel(document, undo_stack=stack)
    index = model.index(0, COLUMN_TEXT)

    assert model.setData(index, "first") is False
    assert stack.canUndo() is False


def test_add_card_without_undo_stack_is_noop():
    model = CardTableModel(_document_with_cards())
    assert model.add_card() is None
    assert model.rowCount() == 2


def test_add_card_pushes_command_and_inserts_row():
    document = _document_with_cards()
    stack = QUndoStack()
    model = CardTableModel(document, undo_stack=stack)

    new_id = model.add_card()

    assert new_id is not None
    assert model.rowCount() == 3
    assert model.card_id_at_row(2) == new_id
    assert stack.canUndo()

    stack.undo()
    assert model.rowCount() == 2


def test_add_card_gets_default_placeholder_text():
    document = _document_with_cards()
    stack = QUndoStack()
    model = CardTableModel(document, undo_stack=stack)

    new_id = model.add_card()

    assert document.get_card(new_id).text == "New Card 3"


def test_add_card_ids_never_collide():
    document = _document_with_cards()
    stack = QUndoStack()
    model = CardTableModel(document, undo_stack=stack)

    new_ids = [model.add_card() for _ in range(50)]

    assert len(set(new_ids)) == 50


def test_remove_cards_at_rows_single():
    document = _document_with_cards()
    stack = QUndoStack()
    model = CardTableModel(document, undo_stack=stack)

    model.remove_cards_at_rows([0])

    assert model.rowCount() == 1
    assert model.card_id_at_row(0) == "c_2"

    stack.undo()
    assert model.rowCount() == 2
    assert model.card_id_at_row(0) == "c_1"


def test_remove_cards_at_rows_multiple_undoes_as_one_step():
    document = _document_with_cards()
    stack = QUndoStack()
    model = CardTableModel(document, undo_stack=stack)

    model.remove_cards_at_rows([0, 1])

    assert model.rowCount() == 0
    assert stack.count() == 1  # grouped into a single macro command

    stack.undo()
    assert model.rowCount() == 2


def test_remove_cards_at_rows_without_undo_stack_is_noop():
    model = CardTableModel(_document_with_cards())
    model.remove_cards_at_rows([0])
    assert model.rowCount() == 2


def test_incident_link_count_for_card_ids():
    document = _document_with_cards()
    document.add_card(Card(id="c_3", text="third"))
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    document.add_link(Link(id="l_2", source="c_2", target="c_3"))
    model = CardTableModel(document)

    assert model.incident_link_count_for_card_ids(["c_1"]) == 1
    assert model.incident_link_count_for_card_ids(["c_2"]) == 2
    assert model.incident_link_count_for_card_ids(["c_1", "c_2"]) == 2
    assert model.incident_link_count_for_card_ids(["c_3"]) == 1


def test_incident_link_count_for_card_ids_with_no_links():
    model = CardTableModel(_document_with_cards())
    assert model.incident_link_count_for_card_ids(["c_1", "c_2"]) == 0


def test_links_column_shows_linked_card_ids():
    document = _document_with_cards()
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    model = CardTableModel(document)

    assert model.index(0, COLUMN_LINKS).data() == "c_2"
    assert model.index(1, COLUMN_LINKS).data() == "c_1"


def test_links_column_empty_when_no_links():
    model = CardTableModel(_document_with_cards())
    assert model.index(0, COLUMN_LINKS).data() == ""


def test_links_column_lists_multiple_linked_cards():
    document = _document_with_cards()
    document.add_card(Card(id="c_3", text="third"))
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    document.add_link(Link(id="l_2", source="c_1", target="c_3"))
    model = CardTableModel(document)

    assert model.index(0, COLUMN_LINKS).data() == "c_2, c_3"


def test_links_column_updates_live_on_link_added_and_removed(qtbot):
    document = _document_with_cards()
    model = CardTableModel(document)
    assert model.index(0, COLUMN_LINKS).data() == ""

    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    assert model.index(0, COLUMN_LINKS).data() == "c_2"

    document.remove_link("l_1")
    assert model.index(0, COLUMN_LINKS).data() == ""


def test_links_column_is_never_editable_even_with_undo_stack():
    document = _document_with_cards()
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    stack = QUndoStack()
    model = CardTableModel(document, undo_stack=stack)

    index = model.index(0, COLUMN_LINKS)
    assert not (model.flags(index) & Qt.ItemFlag.ItemIsEditable)
    assert model.setData(index, "ignored") is False


def test_deleting_linked_card_does_not_crash(qtbot):
    # Regression: Document.remove_card() emits linkRemoved (which we use to
    # refresh the Links column across all rows) before cardRemoved, so
    # mid-cascade there's a window where a row's card_id is still in our
    # cache but already gone from the Document. data() and card_at_row()
    # both need to tolerate that rather than crashing on the stale id.
    document = _document_with_cards()
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    model = CardTableModel(document, undo_stack=QUndoStack())

    document.remove_card("c_1")  # must not raise

    assert model.rowCount() == 1
    assert model.card_id_at_row(0) == "c_2"
    assert model.index(0, COLUMN_LINKS).data() == ""
