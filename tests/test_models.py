import pytest

from indexcards.models.card import Card
from indexcards.models.document import Document
from indexcards.models.link import Link


def _card(card_id: str, **kwargs) -> Card:
    return Card(id=card_id, **kwargs)


def test_add_and_remove_card_emits_signals(qtbot):
    document = Document()
    card = _card("c_1", text="hello")

    with qtbot.waitSignal(document.cardAdded, timeout=1000) as blocker:
        document.add_card(card)
    assert blocker.args == ["c_1"]
    assert document.get_card("c_1") is card

    with qtbot.waitSignal(document.cardRemoved, timeout=1000):
        document.remove_card("c_1")
    assert "c_1" not in document.cards


def test_add_card_duplicate_id_raises():
    document = Document()
    document.add_card(_card("c_1"))
    with pytest.raises(ValueError):
        document.add_card(_card("c_1"))


def test_set_card_text_emits_changed_with_field_name(qtbot):
    document = Document()
    document.add_card(_card("c_1", text="old"))

    with qtbot.waitSignal(document.cardChanged, timeout=1000) as blocker:
        document.set_card_text("c_1", "new")
    assert blocker.args == ["c_1", frozenset({"text"})]
    assert document.get_card("c_1").text == "new"


def test_set_card_text_no_change_does_not_emit(qtbot):
    document = Document()
    document.add_card(_card("c_1", text="same"))

    received = []
    document.cardChanged.connect(lambda *args: received.append(args))
    document.set_card_text("c_1", "same")
    assert received == []


def test_set_card_text_strips_leading_and_trailing_whitespace(qtbot):
    document = Document()
    document.add_card(_card("c_1", text="old"))

    document.set_card_text("c_1", "  padded text  \n")

    assert document.get_card("c_1").text == "padded text"


def test_set_card_text_internal_whitespace_preserved(qtbot):
    document = Document()
    document.add_card(_card("c_1", text="old"))

    document.set_card_text("c_1", "  line one\n\nline two  ")

    assert document.get_card("c_1").text == "line one\n\nline two"


def test_set_card_text_whitespace_only_change_does_not_emit(qtbot):
    document = Document()
    document.add_card(_card("c_1", text="same"))

    received = []
    document.cardChanged.connect(lambda *args: received.append(args))
    document.set_card_text("c_1", "  same  ")

    assert received == []


def test_add_link_rejects_dangling_reference():
    document = Document()
    document.add_card(_card("c_1"))
    with pytest.raises(ValueError):
        document.add_link(Link(id="l_1", source="c_1", target="c_missing"))


def test_add_link_between_existing_cards(qtbot):
    document = Document()
    document.add_card(_card("c_1"))
    document.add_card(_card("c_2"))
    link = Link(id="l_1", source="c_1", target="c_2")

    with qtbot.waitSignal(document.linkAdded, timeout=1000):
        document.add_link(link)
    assert document.get_link("l_1") is link


def test_remove_card_cascades_incident_links():
    document = Document()
    document.add_card(_card("c_1"))
    document.add_card(_card("c_2"))
    document.add_card(_card("c_3"))
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    document.add_link(Link(id="l_2", source="c_2", target="c_3"))
    document.add_link(Link(id="l_3", source="c_1", target="c_3"))

    removed_card, removed_links = document.remove_card("c_1")

    assert removed_card.id == "c_1"
    assert {link.id for link in removed_links} == {"l_1", "l_3"}
    assert "c_1" not in document.cards
    assert set(document.links) == {"l_2"}


def test_bulk_set_positions_moves_all_and_emits_once(qtbot):
    document = Document()
    document.add_card(_card("c_1", x=0, y=0))
    document.add_card(_card("c_2", x=0, y=0))

    with qtbot.waitSignal(document.cardsBulkMoved, timeout=1000) as blocker:
        document.bulk_set_positions({"c_1": (10, 20), "c_2": (30, 40)})

    assert set(blocker.args[0]) == {"c_1", "c_2"}
    assert (document.get_card("c_1").x, document.get_card("c_1").y) == (10, 20)
    assert (document.get_card("c_2").x, document.get_card("c_2").y) == (30, 40)


def test_dirty_tracking(qtbot):
    document = Document()
    assert document.dirty is False

    with qtbot.waitSignal(document.dirtyChanged, timeout=1000) as blocker:
        document.add_card(_card("c_1"))
    assert blocker.args == [True]
    assert document.dirty is True

    document.mark_clean()
    assert document.dirty is False
