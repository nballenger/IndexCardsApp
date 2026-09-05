import pytest

from indexcards.models.card import MAX_TEXT_LENGTH, Card
from indexcards.models.document import DEFAULT_CANVAS_BACKGROUND_COLOR, Document
from indexcards.models.link import Link
from indexcards.models.presets import PRESET_THEMES
from indexcards.models.stack import Stack
from indexcards.models.theme import clone_theme


def _card(card_id: str, **kwargs) -> Card:
    return Card(id=card_id, **kwargs)


def _stack(stack_id: str, **kwargs) -> Stack:
    return Stack(id=stack_id, **kwargs)


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


def test_set_card_text_truncates_to_max_length(qtbot):
    document = Document()
    document.add_card(_card("c_1", text="old"))

    document.set_card_text("c_1", "a" * (MAX_TEXT_LENGTH + 20))

    assert document.get_card("c_1").text == "a" * MAX_TEXT_LENGTH


def test_set_card_text_at_max_length_is_not_truncated(qtbot):
    document = Document()
    document.add_card(_card("c_1", text="old"))

    document.set_card_text("c_1", "a" * MAX_TEXT_LENGTH)

    assert document.get_card("c_1").text == "a" * MAX_TEXT_LENGTH


def test_set_card_text_truncation_strips_first(qtbot):
    document = Document()
    document.add_card(_card("c_1", text="old"))

    # Leading whitespace plus enough 'a's to overflow once stripped —
    # truncation should apply to the stripped result, not count the
    # whitespace toward the limit.
    document.set_card_text("c_1", "  " + "a" * (MAX_TEXT_LENGTH + 5) + "  ")

    assert document.get_card("c_1").text == "a" * MAX_TEXT_LENGTH


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


def test_link_line_ending_defaults_to_none():
    link = Link(id="l_1", source="c_1", target="c_2")
    assert link.line_ending == "none"


def test_set_link_line_ending_emits_signal(qtbot):
    document = Document()
    document.add_card(_card("c_1"))
    document.add_card(_card("c_2"))
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))

    with qtbot.waitSignal(document.linkChanged, timeout=1000) as blocker:
        document.set_link_line_ending("l_1", "to_target")
    assert blocker.args == ["l_1", frozenset({"line_ending"})]
    assert document.get_link("l_1").line_ending == "to_target"


def test_set_link_line_ending_same_value_does_not_emit(qtbot):
    document = Document()
    document.add_card(_card("c_1"))
    document.add_card(_card("c_2"))
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))

    received = []
    document.linkChanged.connect(lambda *args: received.append(args))
    document.set_link_line_ending("l_1", "none")

    assert received == []


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


def test_connected_card_ids_unlinked_card_returns_only_itself():
    document = Document()
    document.add_card(_card("c_1"))

    assert document.connected_card_ids("c_1") == {"c_1"}


def test_connected_card_ids_walks_chain_from_any_node():
    document = Document()
    document.add_card(_card("c_1"))
    document.add_card(_card("c_2"))
    document.add_card(_card("c_3"))
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    document.add_link(Link(id="l_2", source="c_2", target="c_3"))

    expected = {"c_1", "c_2", "c_3"}
    assert document.connected_card_ids("c_1") == expected
    assert document.connected_card_ids("c_2") == expected
    assert document.connected_card_ids("c_3") == expected


def test_connected_card_ids_walks_branching_graph():
    document = Document()
    for card_id in ("c_1", "c_2", "c_3", "c_4"):
        document.add_card(_card(card_id))
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    document.add_link(Link(id="l_2", source="c_1", target="c_3"))
    document.add_link(Link(id="l_3", source="c_3", target="c_4"))

    assert document.connected_card_ids("c_2") == {"c_1", "c_2", "c_3", "c_4"}


def test_connected_card_ids_excludes_disjoint_component():
    document = Document()
    document.add_card(_card("c_1"))
    document.add_card(_card("c_2"))
    document.add_card(_card("c_3"))
    document.add_card(_card("c_4"))
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    document.add_link(Link(id="l_2", source="c_3", target="c_4"))

    assert document.connected_card_ids("c_1") == {"c_1", "c_2"}


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


def test_new_document_defaults_canvas_background_color():
    document = Document()
    assert document.canvas_background_color == DEFAULT_CANVAS_BACKGROUND_COLOR


def _theme_with_background(color: str):
    theme = clone_theme(PRESET_THEMES[0])
    theme.background_color = color
    return theme


def test_document_accepts_custom_theme_background_color():
    document = Document(theme=_theme_with_background("#abcdef"))
    assert document.canvas_background_color == "#abcdef"


def test_document_none_theme_uses_placeholder_preset():
    document = Document(theme=None)
    assert document.canvas_background_color == PRESET_THEMES[0].background_color


def test_document_custom_theme_does_not_mark_dirty():
    # This is the document's initial state, not an edit — it must not go
    # through set_canvas_background_color's dirty-marking/undo-relevant path.
    document = Document(theme=_theme_with_background("#abcdef"))
    assert document.dirty is False


def test_set_canvas_background_color_emits_signal(qtbot):
    document = Document()

    with qtbot.waitSignal(document.backgroundColorChanged, timeout=1000) as blocker:
        document.set_canvas_background_color("#123456")
    assert blocker.args == ["#123456"]
    assert document.canvas_background_color == "#123456"


def test_set_canvas_background_color_same_value_does_not_emit(qtbot):
    document = Document()
    document.set_canvas_background_color("#123456")

    received = []
    document.backgroundColorChanged.connect(received.append)
    document.set_canvas_background_color("#123456")

    assert received == []


def test_set_canvas_background_color_case_insensitive_no_op(qtbot):
    # QColorDialog.getColor().name() always returns lowercase hex, so a
    # differently-cased-but-identical color must not register as a change
    # (regression: this previously pushed a spurious undo step).
    document = Document()
    document.set_canvas_background_color("#ABCDEF")

    received = []
    document.backgroundColorChanged.connect(received.append)
    document.set_canvas_background_color("#abcdef")

    assert received == []


def test_set_theme_link_color_mode_emits_signal(qtbot):
    document = Document()

    with qtbot.waitSignal(document.linkColorModeChanged, timeout=1000) as blocker:
        document.set_theme_link_color_mode("white")
    assert blocker.args == ["white"]
    assert document.theme.link_color_mode == "white"


def test_set_theme_link_color_mode_same_value_does_not_emit(qtbot):
    document = Document()
    document.set_theme_link_color_mode("white")

    received = []
    document.linkColorModeChanged.connect(received.append)
    document.set_theme_link_color_mode("white")

    assert received == []


def test_set_theme_link_weight_emits_signal(qtbot):
    document = Document()

    with qtbot.waitSignal(document.linkWeightChanged, timeout=1000) as blocker:
        document.set_theme_link_weight(5)
    assert blocker.args == [5]
    assert document.theme.link_weight == 5


def test_set_theme_link_weight_same_value_does_not_emit(qtbot):
    document = Document()
    document.set_theme_link_weight(3)

    received = []
    document.linkWeightChanged.connect(received.append)
    document.set_theme_link_weight(3)

    assert received == []


def test_default_line_ending_defaults_to_none():
    document = Document()
    assert document.default_line_ending == "none"


def test_set_default_line_ending_emits_signal(qtbot):
    document = Document()

    with qtbot.waitSignal(document.defaultLineEndingChanged, timeout=1000) as blocker:
        document.set_default_line_ending("both")
    assert blocker.args == ["both"]
    assert document.default_line_ending == "both"


def test_set_default_line_ending_same_value_does_not_emit(qtbot):
    document = Document()
    document.set_default_line_ending("both")

    received = []
    document.defaultLineEndingChanged.connect(received.append)
    document.set_default_line_ending("both")

    assert received == []


def test_set_card_pinned_emits_changed_with_field_name(qtbot):
    document = Document()
    document.add_card(_card("c_1"))

    with qtbot.waitSignal(document.cardChanged, timeout=1000) as blocker:
        document.set_card_pinned("c_1", True)
    assert blocker.args == ["c_1", frozenset({"pinned"})]
    assert document.get_card("c_1").pinned is True


def test_set_card_pinned_no_change_does_not_emit(qtbot):
    document = Document()
    document.add_card(_card("c_1", pinned=True))

    received = []
    document.cardChanged.connect(lambda *args: received.append(args))
    document.set_card_pinned("c_1", True)

    assert received == []


def test_all_pinned_true_when_every_card_pinned():
    document = Document()
    document.add_card(_card("c_1", pinned=True))
    document.add_card(_card("c_2", pinned=True))

    assert document.all_pinned(["c_1", "c_2"]) is True


def test_all_pinned_false_for_mixed_or_unpinned():
    document = Document()
    document.add_card(_card("c_1", pinned=True))
    document.add_card(_card("c_2", pinned=False))

    assert document.all_pinned(["c_1", "c_2"]) is False
    assert document.all_pinned(["c_2"]) is False


def test_all_pinned_false_for_empty_list():
    document = Document()
    assert document.all_pinned([]) is False


def test_set_card_stack_id_emits_changed_with_field_name(qtbot):
    document = Document()
    document.add_card(_card("c_1"))

    with qtbot.waitSignal(document.cardChanged, timeout=1000) as blocker:
        document.set_card_stack_id("c_1", "s_1")
    assert blocker.args == ["c_1", frozenset({"stack_id"})]
    assert document.get_card("c_1").stack_id == "s_1"


def test_set_card_stack_id_no_change_does_not_emit(qtbot):
    document = Document()
    document.add_card(_card("c_1", stack_id="s_1"))

    received = []
    document.cardChanged.connect(lambda *args: received.append(args))
    document.set_card_stack_id("c_1", "s_1")

    assert received == []


def test_add_and_remove_stack_emits_signals(qtbot):
    document = Document()
    stack = _stack("s_1")

    with qtbot.waitSignal(document.stackAdded, timeout=1000) as blocker:
        document.add_stack(stack)
    assert blocker.args == ["s_1"]
    assert document.get_stack("s_1") is stack

    with qtbot.waitSignal(document.stackRemoved, timeout=1000):
        document.remove_stack("s_1")
    assert "s_1" not in document.stacks


def test_add_stack_duplicate_id_raises():
    document = Document()
    document.add_stack(_stack("s_1"))
    with pytest.raises(ValueError):
        document.add_stack(_stack("s_1"))


def test_add_stack_at_index_restores_original_position():
    document = Document()
    document.add_stack(_stack("s_1"))
    document.add_stack(_stack("s_2"))
    document.remove_stack("s_1")

    document.add_stack(_stack("s_1"), index=0)

    assert list(document.stacks.keys()) == ["s_1", "s_2"]


def test_remove_stack_does_not_touch_member_cards():
    document = Document()
    document.add_card(_card("c_1", stack_id="s_1"))
    document.add_stack(_stack("s_1", card_ids=["c_1"]))

    document.remove_stack("s_1")

    assert document.get_card("c_1").stack_id == "s_1"  # caller's job to clear this


def test_set_stack_label_emits_changed_with_field_name(qtbot):
    document = Document()
    document.add_stack(_stack("s_1"))

    with qtbot.waitSignal(document.stackChanged, timeout=1000) as blocker:
        document.set_stack_label("s_1", "Chapter 1")
    assert blocker.args == ["s_1", frozenset({"label"})]
    assert document.get_stack("s_1").label == "Chapter 1"


def test_set_stack_label_strips_whitespace():
    document = Document()
    document.add_stack(_stack("s_1"))

    document.set_stack_label("s_1", "  padded  ")

    assert document.get_stack("s_1").label == "padded"


def test_set_stack_label_no_change_does_not_emit(qtbot):
    document = Document()
    document.add_stack(_stack("s_1", label="same"))

    received = []
    document.stackChanged.connect(lambda *args: received.append(args))
    document.set_stack_label("s_1", "same")

    assert received == []


def test_set_stack_position_emits_moved(qtbot):
    document = Document()
    document.add_stack(_stack("s_1"))

    with qtbot.waitSignal(document.stackMoved, timeout=1000) as blocker:
        document.set_stack_position("s_1", 10.0, 20.0)
    assert blocker.args == ["s_1"]
    assert (document.get_stack("s_1").x, document.get_stack("s_1").y) == (10.0, 20.0)


def test_bulk_set_stack_positions_moves_all_and_emits_once(qtbot):
    document = Document()
    document.add_stack(_stack("s_1"))
    document.add_stack(_stack("s_2"))

    with qtbot.waitSignal(document.stacksBulkMoved, timeout=1000) as blocker:
        document.bulk_set_stack_positions({"s_1": (10, 20), "s_2": (30, 40)})

    assert set(blocker.args[0]) == {"s_1", "s_2"}
    assert (document.get_stack("s_1").x, document.get_stack("s_1").y) == (10, 20)
    assert (document.get_stack("s_2").x, document.get_stack("s_2").y) == (30, 40)


def test_add_cards_to_stack_sets_stack_id_and_unpins(qtbot):
    document = Document()
    document.add_card(_card("c_1", pinned=True))
    document.add_stack(_stack("s_1"))

    with qtbot.waitSignal(document.stackChanged, timeout=1000) as blocker:
        document.add_cards_to_stack("s_1", ["c_1"])

    assert blocker.args == ["s_1", frozenset({"card_ids"})]
    assert document.get_card("c_1").stack_id == "s_1"
    assert document.get_card("c_1").pinned is False
    assert document.get_stack("s_1").card_ids == ["c_1"]


def test_add_cards_to_stack_is_idempotent_for_already_member_cards(qtbot):
    document = Document()
    document.add_card(_card("c_1"))
    document.add_stack(_stack("s_1"))
    document.add_cards_to_stack("s_1", ["c_1"])

    received = []
    document.stackChanged.connect(lambda *args: received.append(args))
    document.add_cards_to_stack("s_1", ["c_1"])

    assert received == []
    assert document.get_stack("s_1").card_ids == ["c_1"]


def test_add_cards_to_stack_severs_link_to_card_outside_stack(qtbot):
    document = Document()
    document.add_card(_card("c_1"))
    document.add_card(_card("c_2"))
    document.add_stack(_stack("s_1"))
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))

    with qtbot.waitSignal(document.linkRemoved, timeout=1000) as blocker:
        removed = document.add_cards_to_stack("s_1", ["c_1"])

    assert blocker.args == ["l_1"]
    assert "l_1" not in document.links
    assert [link.id for link in removed] == ["l_1"]


def test_add_cards_to_stack_severs_mutual_link_between_cards_joining_together(qtbot):
    document = Document()
    document.add_card(_card("c_1"))
    document.add_card(_card("c_2"))
    document.add_stack(_stack("s_1"))
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))

    removed = document.add_cards_to_stack("s_1", ["c_1", "c_2"])

    assert [link.id for link in removed] == ["l_1"]
    assert document.links == {}


def test_add_cards_to_stack_returns_empty_list_with_no_incident_links(qtbot):
    document = Document()
    document.add_card(_card("c_1"))
    document.add_stack(_stack("s_1"))

    received = []
    document.linkRemoved.connect(lambda *args: received.append(args))
    removed = document.add_cards_to_stack("s_1", ["c_1"])

    assert removed == []
    assert received == []


def test_add_cards_to_stack_no_link_cascade_for_redundant_membership(qtbot):
    document = Document()
    document.add_card(_card("c_1"))
    document.add_card(_card("c_2"))
    document.add_stack(_stack("s_1"))
    document.add_cards_to_stack("s_1", ["c_1"])
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))

    # c_1 already belongs to s_1 before this link existed; re-adding it to
    # the same stack (a redundant call) still severs a link that now
    # exists on it, matching "putting a card on a stack severs its links"
    # rather than only severing on the card's very first join.
    removed = document.add_cards_to_stack("s_1", ["c_1"])

    assert [link.id for link in removed] == ["l_1"]
    assert document.links == {}


def test_remove_cards_from_stack_clears_stack_id(qtbot):
    document = Document()
    document.add_card(_card("c_1", stack_id="s_1"))
    document.add_stack(_stack("s_1", card_ids=["c_1"]))

    with qtbot.waitSignal(document.stackChanged, timeout=1000) as blocker:
        document.remove_cards_from_stack("s_1", ["c_1"])

    assert blocker.args == ["s_1", frozenset({"card_ids"})]
    assert document.get_card("c_1").stack_id is None
    assert document.get_stack("s_1").card_ids == []


def test_remove_cards_from_stack_tolerates_already_deleted_card():
    document = Document()
    document.add_stack(_stack("s_1", card_ids=["c_missing"]))

    document.remove_cards_from_stack("s_1", ["c_missing"])

    assert document.get_stack("s_1").card_ids == []
