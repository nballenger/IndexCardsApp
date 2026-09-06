from indexcards.models.card import Card
from indexcards.models.document import Document
from indexcards.models.link import Link
from indexcards.models.stack import Stack
from indexcards.persistence.validation import repair_document


def _document_with_card(card_id: str = "c_1", **kwargs) -> Document:
    document = Document(name="Test")
    document.cards[card_id] = Card(id=card_id, **kwargs)
    return document


def test_clean_document_returns_no_messages():
    document = _document_with_card()
    document.cards["c_1"].color_slot = document.theme.slots[0].id

    messages = repair_document(document)

    assert messages == []


def test_unknown_color_slot_is_reset_to_first_theme_slot():
    document = _document_with_card(color_slot="slot_does_not_exist")
    expected = document.theme.slots[0].id

    messages = repair_document(document)

    assert document.get_card("c_1").color_slot == expected
    assert len(messages) == 1
    assert "slot_does_not_exist" in messages[0]
    assert "c_1" in messages[0]


def test_dangling_link_is_removed():
    document = _document_with_card("c_1")
    document.cards["c_2"] = Card(id="c_2")
    document.links["l_1"] = Link(id="l_1", source="c_1", target="c_2")
    document.links["l_2"] = Link(id="l_2", source="c_1", target="c_missing")

    messages = repair_document(document)

    assert "l_1" in document.links
    assert "l_2" not in document.links
    assert len(messages) == 1
    assert "l_2" in messages[0]
    assert "c_missing" in messages[0]


def test_dangling_stack_member_is_dropped():
    document = _document_with_card("c_1")
    document.stacks["s_1"] = Stack(id="s_1", card_ids=["c_1", "c_missing"])
    document.cards["c_1"].stack_id = "s_1"

    messages = repair_document(document)

    assert document.get_stack("s_1").card_ids == ["c_1"]
    assert len(messages) == 1
    assert "c_missing" in messages[0]


def test_stack_id_cleared_when_no_stack_lists_the_card():
    document = _document_with_card("c_1", stack_id="s_1")
    # No stack "s_1" exists at all.

    messages = repair_document(document)

    assert document.get_card("c_1").stack_id is None
    assert len(messages) == 1
    assert "c_1" in messages[0]
    assert "s_1" in messages[0]


def test_stack_id_set_when_card_is_listed_but_had_none():
    document = _document_with_card("c_1", stack_id=None)
    document.stacks["s_1"] = Stack(id="s_1", card_ids=["c_1"])

    messages = repair_document(document)

    assert document.get_card("c_1").stack_id == "s_1"
    assert len(messages) == 1
    assert "c_1" in messages[0]
    assert "s_1" in messages[0]


def test_stack_id_corrected_when_it_disagrees_with_actual_membership():
    document = _document_with_card("c_1", stack_id="s_wrong")
    document.stacks["s_1"] = Stack(id="s_1", card_ids=["c_1"])

    messages = repair_document(document)

    assert document.get_card("c_1").stack_id == "s_1"
    assert len(messages) == 1
    assert "s_wrong" in messages[0]
    assert "s_1" in messages[0]


def test_multiple_issues_all_reported():
    document = _document_with_card("c_1", color_slot="slot_bad")
    # c_2's stack_id already agrees with s_1's card_ids below, so this
    # exercises exactly the 3 issues under test -- not a 4th, incidental
    # stack_id-mismatch repair.
    document.cards["c_2"] = Card(id="c_2", stack_id="s_1")
    document.links["l_1"] = Link(id="l_1", source="c_1", target="c_missing")
    document.stacks["s_1"] = Stack(id="s_1", card_ids=["c_2", "c_missing"])

    messages = repair_document(document)

    assert len(messages) == 3
