from indexcards.list_view.card_table_model import (
    COLUMN_COLOR,
    COLUMN_TAGS,
    COLUMN_TEXT,
    CardTableModel,
)
from indexcards.models.card import Card
from indexcards.models.document import Document


def _document_with_cards() -> Document:
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="first", color="#F6E27A", tags=["a", "b"]))
    document.add_card(Card(id="c_2", text="second", color="#A8D8F0", tags=[]))
    return document


def test_row_and_column_counts():
    model = CardTableModel(_document_with_cards())
    assert model.rowCount() == 2
    assert model.columnCount() == 3


def test_data_returns_text_color_and_joined_tags():
    model = CardTableModel(_document_with_cards())

    assert model.index(0, COLUMN_TEXT).data() == "first"
    assert model.index(0, COLUMN_COLOR).data() == "#F6E27A"
    assert model.index(0, COLUMN_TAGS).data() == "a, b"
    assert model.index(1, COLUMN_TAGS).data() == ""


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
