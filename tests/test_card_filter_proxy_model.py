from indexcards.list_view.card_filter_proxy_model import CardFilterProxyModel
from indexcards.list_view.card_table_model import COLUMN_COLOR, CardTableModel
from indexcards.models.card import Card
from indexcards.models.document import Document


def _document_with_cards() -> Document:
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="A story about time travel", tags=["plot"]))
    document.add_card(Card(id="c_2", text="Character sketch", tags=["character", "urgent"]))
    document.add_card(Card(id="c_3", text="Loose thought", tags=[]))
    return document


def test_empty_query_shows_all_rows(qtbot):
    document = _document_with_cards()
    model = CardTableModel(document)
    proxy = CardFilterProxyModel()
    proxy.setSourceModel(model)

    assert proxy.rowCount() == 3


def test_query_filters_by_text(qtbot):
    document = _document_with_cards()
    model = CardTableModel(document)
    proxy = CardFilterProxyModel()
    proxy.setSourceModel(model)

    proxy.set_query("time travel")

    assert proxy.rowCount() == 1
    source_row = proxy.mapToSource(proxy.index(0, 0)).row()
    assert model.card_id_at_row(source_row) == "c_1"


def test_query_does_not_filter_by_tag_by_default(qtbot):
    document = _document_with_cards()
    model = CardTableModel(document)
    proxy = CardFilterProxyModel()
    proxy.setSourceModel(model)

    proxy.set_query("urgent")

    assert proxy.rowCount() == 0


def test_query_filters_by_tag_when_tags_enabled(qtbot, monkeypatch):
    monkeypatch.setattr("indexcards.search.TAGS_ENABLED", True)
    document = _document_with_cards()
    model = CardTableModel(document)
    proxy = CardFilterProxyModel()
    proxy.setSourceModel(model)

    proxy.set_query("urgent")

    assert proxy.rowCount() == 1
    source_row = proxy.mapToSource(proxy.index(0, 0)).row()
    assert model.card_id_at_row(source_row) == "c_2"


def test_clearing_query_restores_all_rows(qtbot):
    document = _document_with_cards()
    model = CardTableModel(document)
    proxy = CardFilterProxyModel()
    proxy.setSourceModel(model)

    proxy.set_query("time travel")
    assert proxy.rowCount() == 1

    proxy.set_query("")
    assert proxy.rowCount() == 3


def test_color_column_sorts_by_palette_order_not_hex_string(qtbot):
    # Lexicographically "#A8D8F0" (Blue) < "#FFFFFF" (White), the opposite
    # of PALETTE order (White is first, Blue is third) — this only passes
    # if lessThan() actually consults palette position, not the hex text.
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="a", color="#A8D8F0"))  # Blue
    document.add_card(Card(id="c_2", text="b", color="#FFFFFF"))  # White
    model = CardTableModel(document)
    proxy = CardFilterProxyModel()
    proxy.setSourceModel(model)

    proxy.sort(COLUMN_COLOR)

    assert model.card_id_at_row(proxy.mapToSource(proxy.index(0, 0)).row()) == "c_2"
    assert model.card_id_at_row(proxy.mapToSource(proxy.index(1, 0)).row()) == "c_1"
