from indexcards.list_view.card_filter_proxy_model import CardFilterProxyModel
from indexcards.list_view.card_table_model import COLUMN_COLOR, CardTableModel
from indexcards.models.card import Card
from indexcards.models.document import Document
from indexcards.models.theme import Slot


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


def test_default_active_stack_shows_only_unstacked_cards(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1"))
    document.add_card(Card(id="c_2", stack_id="s_1"))
    model = CardTableModel(document)
    proxy = CardFilterProxyModel()
    proxy.setSourceModel(model)

    assert proxy.rowCount() == 1
    source_row = proxy.mapToSource(proxy.index(0, 0)).row()
    assert model.card_id_at_row(source_row) == "c_1"


def test_set_active_stack_id_shows_only_that_stacks_cards(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1"))
    document.add_card(Card(id="c_2", stack_id="s_1"))
    document.add_card(Card(id="c_3", stack_id="s_2"))
    model = CardTableModel(document)
    proxy = CardFilterProxyModel()
    proxy.setSourceModel(model)

    proxy.set_active_stack_id("s_1")

    assert proxy.rowCount() == 1
    source_row = proxy.mapToSource(proxy.index(0, 0)).row()
    assert model.card_id_at_row(source_row) == "c_2"


def test_active_stack_id_combines_with_search_query(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="dragon", stack_id="s_1"))
    document.add_card(Card(id="c_2", text="castle", stack_id="s_1"))
    model = CardTableModel(document)
    proxy = CardFilterProxyModel()
    proxy.setSourceModel(model)
    proxy.set_active_stack_id("s_1")

    proxy.set_query("dragon")

    assert proxy.rowCount() == 1
    source_row = proxy.mapToSource(proxy.index(0, 0)).row()
    assert model.card_id_at_row(source_row) == "c_1"


def test_set_active_stack_id_same_value_does_not_invalidate(qtbot):
    document = Document(name="Test")
    document.add_card(Card(id="c_1"))
    model = CardTableModel(document)
    proxy = CardFilterProxyModel()
    proxy.setSourceModel(model)

    layout_changes = []
    proxy.layoutChanged.connect(lambda *a: layout_changes.append(a))
    proxy.set_active_stack_id(None)  # already the default

    assert layout_changes == []


def test_color_column_sorts_by_theme_slot_order_not_slot_id_string(qtbot):
    # Lexicographically "slot_blue" < "slot_white", the opposite of the
    # theme's own slot order (White is first, Blue is third) — this only
    # passes if lessThan() actually consults theme slot position, not the
    # slot id text.
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="a", color_slot="slot_blue"))
    document.add_card(Card(id="c_2", text="b", color_slot="slot_white"))
    model = CardTableModel(document)
    proxy = CardFilterProxyModel()
    proxy.setSourceModel(model)

    proxy.sort(COLUMN_COLOR)

    assert model.card_id_at_row(proxy.mapToSource(proxy.index(0, 0)).row()) == "c_2"
    assert model.card_id_at_row(proxy.mapToSource(proxy.index(1, 0)).row()) == "c_1"


def test_color_column_sorts_orphaned_slots_after_active_ones(qtbot):
    document = Document(name="Test")
    document.theme.slots.append(Slot(id="slot_custom", label="Custom", hex="#123abc"))
    document.theme.slots[-1].orphaned = True
    # "slot_custom" would sort before every "slot_*" preset id alphabetically,
    # so this only passes if lessThan() puts orphaned slots after active ones.
    document.add_card(Card(id="c_1", text="a", color_slot="slot_custom"))
    document.add_card(Card(id="c_2", text="b", color_slot="slot_gray"))
    model = CardTableModel(document)
    proxy = CardFilterProxyModel()
    proxy.setSourceModel(model)

    proxy.sort(COLUMN_COLOR)

    assert model.card_id_at_row(proxy.mapToSource(proxy.index(0, 0)).row()) == "c_2"
    assert model.card_id_at_row(proxy.mapToSource(proxy.index(1, 0)).row()) == "c_1"
