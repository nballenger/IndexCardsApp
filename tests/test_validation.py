from indexcards.models.card import Card
from indexcards.models.document import Document
from indexcards.models.link import Link
from indexcards.models.reference import Reference
from indexcards.models.region import MIN_REGION_SIZE, Region
from indexcards.models.stack import Stack
from indexcards.persistence.validation import repair_document
from indexcards.regions.geometry import has_room_for_card, intersect, to_rect


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


def test_well_formed_references_are_untouched():
    document = _document_with_card(
        color_slot="slot_white",
        references=[Reference(text="A", url="https://a.example"), Reference(url="https://b.example")],
    )
    document.cards["c_1"].color_slot = document.theme.slots[0].id

    messages = repair_document(document)

    assert messages == []
    assert len(document.get_card("c_1").references) == 2


def test_fully_blank_reference_is_dropped_and_valid_one_kept():
    document = _document_with_card(
        references=[Reference(), Reference(text="Kept")],
    )
    document.cards["c_1"].color_slot = document.theme.slots[0].id

    messages = repair_document(document)

    assert document.get_card("c_1").references == [Reference(text="Kept")]
    assert len(messages) == 1
    assert "blank" in messages[0]


def test_more_than_two_references_are_truncated_to_first_two():
    document = _document_with_card(
        references=[Reference(text="A"), Reference(text="B"), Reference(text="C")],
    )
    document.cards["c_1"].color_slot = document.theme.slots[0].id

    messages = repair_document(document)

    assert document.get_card("c_1").references == [Reference(text="A"), Reference(text="B")]
    assert len(messages) == 1
    assert "first 2" in messages[0]


def test_undersized_region_is_enlarged_to_minimum():
    document = Document(name="Test")
    document.regions["r_1"] = Region(id="r_1", width=10.0, height=10.0)

    messages = repair_document(document)

    region = document.regions["r_1"]
    assert (region.width, region.height) == MIN_REGION_SIZE
    assert len(messages) == 1
    assert "r_1" in messages[0]


def test_well_formed_region_is_untouched():
    document = Document(name="Test")
    document.regions["r_1"] = Region(id="r_1", width=300.0, height=200.0)

    messages = repair_document(document)

    region = document.regions["r_1"]
    assert (region.width, region.height) == (300.0, 200.0)
    assert messages == []


def test_regions_with_a_too_thin_overlap_are_grown_and_reported():
    document = Document(name="Test")
    document.regions["a"] = Region(id="a", x=0.0, y=0.0, width=300.0, height=200.0)
    document.regions["b"] = Region(id="b", x=280.0, y=0.0, width=300.0, height=200.0)

    messages = repair_document(document)

    a, b = document.regions["a"], document.regions["b"]
    overlap = intersect(to_rect(a), to_rect(b))
    assert overlap is not None
    assert has_room_for_card(overlap)
    assert any("'a'" in m and "enlarged" in m for m in messages)
    assert any("'b'" in m and "enlarged" in m for m in messages)


def test_regions_with_a_too_tight_moat_are_grown_and_reported():
    document = Document(name="Test")
    document.regions["outer"] = Region(id="outer", x=0.0, y=0.0, width=300.0, height=200.0)
    document.regions["inner"] = Region(id="inner", x=10.0, y=10.0, width=250.0, height=160.0)

    messages = repair_document(document)

    assert document.regions["outer"].height > 200.0
    assert document.regions["inner"].width == 250.0  # child never moves/shrinks
    assert any("'outer'" in m and "enlarged" in m for m in messages)


def test_well_separated_regions_produce_no_pairwise_messages():
    document = Document(name="Test")
    document.regions["a"] = Region(id="a", x=0.0, y=0.0, width=300.0, height=200.0)
    document.regions["b"] = Region(id="b", x=1000.0, y=1000.0, width=300.0, height=200.0)

    messages = repair_document(document)

    assert messages == []


def test_an_undersized_region_that_still_violates_a_pairwise_invariant_gets_both_fixes():
    # 'a' is individually undersized (needs the MIN_REGION_SIZE clamp
    # first) and, only once clamped, overlaps 'b' too thinly -- exercises
    # the order the two repair steps must run in.
    document = Document(name="Test")
    document.regions["a"] = Region(id="a", x=0.0, y=0.0, width=10.0, height=10.0)
    document.regions["b"] = Region(id="b", x=200.0, y=0.0, width=300.0, height=200.0)

    messages = repair_document(document)

    a, b = document.regions["a"], document.regions["b"]
    assert a.width >= MIN_REGION_SIZE[0]
    assert a.height >= MIN_REGION_SIZE[1]
    overlap = intersect(to_rect(a), to_rect(b))
    assert overlap is not None
    assert has_room_for_card(overlap)
    assert any("smaller than the minimum size" in m for m in messages)
    assert any("met another region" in m for m in messages)


def test_repair_region_geometry_giving_up_is_reported_and_leaves_regions_alone(monkeypatch):
    monkeypatch.setattr(
        "indexcards.persistence.validation.repair_region_geometry", lambda regions: None
    )
    document = Document(name="Test")
    document.regions["a"] = Region(id="a", x=0.0, y=0.0, width=300.0, height=200.0)
    document.regions["b"] = Region(id="b", x=1000.0, y=1000.0, width=300.0, height=200.0)
    original = {(r.x, r.y, r.width, r.height) for r in document.regions.values()}

    messages = repair_document(document)

    assert {(r.x, r.y, r.width, r.height) for r in document.regions.values()} == original
    assert any("could not be automatically resized" in m for m in messages)


def test_straddling_loose_card_is_moved_fully_outside_and_reported():
    document = Document(name="Test")
    document.regions["r_1"] = Region(id="r_1", x=0.0, y=0.0, width=300.0, height=200.0)
    document.cards["c_1"] = Card(id="c_1", x=250.0, y=50.0)

    messages = repair_document(document)

    card = document.cards["c_1"]
    assert (card.x, card.y) == (300.0, 50.0)
    assert any("'c_1'" in m and "straddled" in m for m in messages)


def test_straddling_stack_is_moved_fully_outside_and_reported():
    document = Document(name="Test")
    document.regions["r_1"] = Region(id="r_1", x=0.0, y=0.0, width=300.0, height=200.0)
    document.stacks["s_1"] = Stack(id="s_1", x=250.0, y=50.0)

    messages = repair_document(document)

    stack = document.stacks["s_1"]
    assert (stack.x, stack.y) == (300.0, 50.0)
    assert any("'s_1'" in m and "straddled" in m for m in messages)


def test_card_fully_outside_every_region_is_untouched():
    document = Document(name="Test")
    document.regions["r_1"] = Region(id="r_1", x=0.0, y=0.0, width=300.0, height=200.0)
    document.cards["c_1"] = Card(id="c_1", x=5000.0, y=5000.0)

    messages = repair_document(document)

    assert (document.cards["c_1"].x, document.cards["c_1"].y) == (5000.0, 5000.0)
    assert messages == []


def test_stacked_card_positions_are_never_touched_by_straddle_repair():
    document = Document(name="Test")
    document.regions["r_1"] = Region(id="r_1", x=0.0, y=0.0, width=300.0, height=200.0)
    document.stacks["s_1"] = Stack(id="s_1", x=1000.0, y=1000.0, card_ids=["c_1"])
    document.cards["c_1"] = Card(id="c_1", x=250.0, y=50.0, stack_id="s_1")

    messages = repair_document(document)

    assert (document.cards["c_1"].x, document.cards["c_1"].y) == (250.0, 50.0)
    assert not any("'c_1'" in m for m in messages)


def test_unresolvable_straddle_is_left_in_place_and_reported(monkeypatch):
    monkeypatch.setattr(
        "indexcards.persistence.validation.resolve_drop_against_regions",
        lambda rect, regions, max_iterations=50: None,
    )
    document = Document(name="Test")
    document.regions["r_1"] = Region(id="r_1", x=0.0, y=0.0, width=300.0, height=200.0)
    document.cards["c_1"] = Card(id="c_1", x=250.0, y=50.0)

    messages = repair_document(document)

    assert (document.cards["c_1"].x, document.cards["c_1"].y) == (250.0, 50.0)
    assert any("'c_1'" in m and "couldn't be moved" in m for m in messages)
