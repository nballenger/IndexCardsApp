import json

import pytest

from indexcards.models.card import MAX_TEXT_LENGTH, Card
from indexcards.models.document import Document
from indexcards.models.presets import PRESET_THEMES
from indexcards.models.stack import Stack
from indexcards.models.theme import clone_theme
from indexcards.utils.clipboard_format import (
    CLIPBOARD_FORMAT_VERSION,
    build_clipboard_payload,
    card_texts_from_plain_text,
    cards_and_stacks_from_payload,
    plain_text_for_payload,
    resolve_color_slot,
)


def _document_with_selection() -> Document:
    document = Document(name="Test", theme=clone_theme(PRESET_THEMES[0]))
    slot_id = document.theme.slots[0].id
    document.add_card(Card(id="c_1", text="Loose One", x=0.0, y=0.0, color_slot=slot_id))
    document.add_card(Card(id="c_2", text="Loose Two", x=100.0, y=0.0, color_slot=slot_id))
    document.add_card(
        Card(id="c_3", text="Member One", x=200.0, y=200.0, color_slot=slot_id, stack_id="s_1")
    )
    document.add_card(
        Card(id="c_4", text="Member Two", x=200.0, y=200.0, color_slot=slot_id, stack_id="s_1")
    )
    document.add_stack(
        Stack(id="s_1", card_ids=["c_3", "c_4"], x=200.0, y=200.0, label="My Stack")
    )
    return document


def test_build_clipboard_payload_shape():
    document = _document_with_selection()
    payload = build_clipboard_payload(document, ["c_1", "c_2"], ["s_1"])

    assert payload["version"] == CLIPBOARD_FORMAT_VERSION
    assert [c["text"] for c in payload["cards"]] == ["Loose One", "Loose Two"]
    assert len(payload["stacks"]) == 1
    stack_payload = payload["stacks"][0]
    assert stack_payload["label"] == "My Stack"
    assert [c["text"] for c in stack_payload["cards"]] == ["Member One", "Member Two"]


def test_build_clipboard_payload_carries_hex_not_theme_local_slot_id():
    document = _document_with_selection()
    payload = build_clipboard_payload(document, ["c_1"], [])
    card_payload = payload["cards"][0]
    assert "color_slot" not in card_payload
    assert card_payload["color_hex"] == document.get_slot(document.theme.slots[0].id).hex


def test_plain_text_for_payload_orders_loose_cards_then_stack_as_header_and_bullets():
    document = _document_with_selection()
    payload = build_clipboard_payload(document, ["c_1", "c_2"], ["s_1"])
    assert plain_text_for_payload(payload) == (
        "Loose One\nLoose Two\nIndexCards Stack: My Stack\n* Member One\n* Member Two"
    )


def test_resolve_color_slot_matches_by_hex_case_insensitively():
    theme = clone_theme(PRESET_THEMES[0])
    target_slot = theme.slots[2]
    resolved = resolve_color_slot(theme, target_slot.hex.upper(), target_slot.label)
    assert resolved == target_slot.id


def test_resolve_color_slot_falls_back_to_first_slot_when_no_match():
    theme = clone_theme(PRESET_THEMES[0])
    resolved = resolve_color_slot(theme, "#123456", "Not A Real Color")
    assert resolved == theme.slots[0].id


def test_cards_and_stacks_from_payload_round_trips_with_fresh_ids():
    source = _document_with_selection()
    payload = json.loads(json.dumps(build_clipboard_payload(source, ["c_1", "c_2"], ["s_1"])))

    destination = Document(name="Dest", theme=clone_theme(PRESET_THEMES[0]))
    existing_ids = set(destination.cards) | set(destination.stacks)
    cards, stacks = cards_and_stacks_from_payload(payload, destination.theme, existing_ids)

    assert [c.text for c in cards] == ["Loose One", "Loose Two"]
    assert {c.id for c in cards}.isdisjoint({"c_1", "c_2", "c_3", "c_4"})
    assert len(stacks) == 1
    stack, members = stacks[0]
    assert stack.label == "My Stack"
    assert stack.card_ids == [member.id for member in members]
    assert all(member.stack_id == stack.id for member in members)
    assert stack.id != "s_1"


def test_cards_and_stacks_from_payload_never_collides_with_existing_ids():
    source = _document_with_selection()
    payload = build_clipboard_payload(source, ["c_1", "c_2"], ["s_1"])
    # Same document, same ids already present -- a "paste to duplicate" scenario.
    existing_ids = set(source.cards) | set(source.stacks)
    original_existing_ids = set(existing_ids)

    cards, stacks = cards_and_stacks_from_payload(payload, source.theme, existing_ids)

    new_card_ids = {c.id for c in cards}
    stack, members = stacks[0]
    new_ids = new_card_ids | {stack.id} | {m.id for m in members}
    assert new_ids.isdisjoint(original_existing_ids)


def test_cards_and_stacks_from_payload_resolves_color_per_destination_theme():
    source = _document_with_selection()
    payload = build_clipboard_payload(source, ["c_1"], [])
    destination_theme = clone_theme(PRESET_THEMES[1])  # a different palette entirely

    cards, _stacks = cards_and_stacks_from_payload(payload, destination_theme, set())

    assert cards[0].color_slot in {slot.id for slot in destination_theme.slots}


def test_cards_and_stacks_from_payload_rejects_wrong_version():
    payload = {"version": 999, "cards": [], "stacks": []}
    with pytest.raises(ValueError):
        cards_and_stacks_from_payload(payload, clone_theme(PRESET_THEMES[0]), set())


def test_cards_and_stacks_from_payload_rejects_malformed_shape():
    with pytest.raises(ValueError):
        cards_and_stacks_from_payload(
            {"version": CLIPBOARD_FORMAT_VERSION, "cards": "not a list"},
            clone_theme(PRESET_THEMES[0]),
            set(),
        )


def test_card_texts_from_plain_text_strips_and_drops_blank_lines():
    text = "  First  \n\n   \nSecond\nThird   "
    assert card_texts_from_plain_text(text) == ["First", "Second", "Third"]


def test_card_texts_from_plain_text_truncates_to_max_length():
    long_line = "x" * (MAX_TEXT_LENGTH + 50)
    result = card_texts_from_plain_text(long_line)
    assert result == [long_line[:MAX_TEXT_LENGTH]]
    assert len(result[0]) == MAX_TEXT_LENGTH


def test_card_texts_from_plain_text_empty_string_returns_empty_list():
    assert card_texts_from_plain_text("") == []
    assert card_texts_from_plain_text("   \n  \n") == []


def test_plain_text_for_payload_escapes_a_cards_own_newlines():
    document = _document_with_selection()
    document.set_card_text("c_1", "Line one\nLine two")
    payload = build_clipboard_payload(document, ["c_1"], [])

    text = plain_text_for_payload(payload)

    # One physical line for the card -- its own newline survives only as
    # a literal backslash-n, not a real line break.
    assert text == "Line one\\nLine two"
    assert "\n" not in text


def test_card_texts_from_plain_text_unescapes_a_cards_own_newlines():
    # The exact inverse of the escaping test above -- what a card looks
    # like after being copied out, pasted into another app, copied again,
    # and pasted back into IndexCards.
    assert card_texts_from_plain_text("Line one\\nLine two") == ["Line one\nLine two"]


def test_newline_round_trip_through_plain_text_reconstructs_one_card():
    document = _document_with_selection()
    document.set_card_text("c_1", "Line one\nLine two\nLine three")
    payload = build_clipboard_payload(document, ["c_1"], [])

    exported = plain_text_for_payload(payload)
    reconstructed = card_texts_from_plain_text(exported)

    assert reconstructed == ["Line one\nLine two\nLine three"]


def test_plain_text_list_pasted_from_elsewhere_still_splits_one_card_per_line():
    # The other half of the same tradeoff: an ordinary multi-item list
    # typed in another app (no backslash-n sequences at all) must keep
    # splitting into one card per physical line, unaffected by unescaping.
    text = "Apple\nBanana\nCherry"
    assert card_texts_from_plain_text(text) == ["Apple", "Banana", "Cherry"]


def test_plain_text_for_payload_stack_header_and_bullets_exact_format():
    document = _document_with_selection()
    payload = build_clipboard_payload(document, [], ["s_1"])

    assert plain_text_for_payload(payload) == (
        "IndexCards Stack: My Stack\n* Member One\n* Member Two"
    )


def test_card_texts_from_plain_text_drops_stack_header_line():
    text = "IndexCards Stack: My Stack\n* Member One\n* Member Two"
    assert card_texts_from_plain_text(text) == ["Member One", "Member Two"]


def test_card_texts_from_plain_text_strips_bullet_prefix_only_at_line_start():
    # A card whose own text happens to start with "* " for some other
    # reason is indistinguishable from a bullet line once it's plain text
    # -- an accepted, narrow ambiguity of the exported format, not a bug.
    text = "* Not a stack, just a card starting with an asterisk"
    expected = "Not a stack, just a card starting with an asterisk"
    assert card_texts_from_plain_text(text) == [expected]
