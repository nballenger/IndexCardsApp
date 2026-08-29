from PySide6.QtGui import QUndoStack

from indexcards.commands.arrange_commands import AutoArrangeCommand
from indexcards.commands.card_commands import (
    AddCardCommand,
    ChangeColorCommand,
    ChangeTagsCommand,
    DeleteCardCommand,
    EditCardTextCommand,
    TogglePinCommand,
)
from indexcards.commands.document_commands import ChangeCanvasBackgroundCommand
from indexcards.commands.link_commands import AddLinkCommand, DeleteLinkCommand
from indexcards.commands.move_commands import MoveCardCommand, MoveCardsCommand, MoveStackCommand
from indexcards.commands.stack_commands import (
    AddCardsToStackCommand,
    ChangeStackLabelCommand,
    CreateStackCommand,
    ExplodeStackCommand,
    GatherStacksCommand,
    RemoveStackCommand,
    push_delete_stack_and_cards,
)
from indexcards.models.card import Card
from indexcards.models.document import Document
from indexcards.models.link import Link
from indexcards.models.stack import Stack


def _document_with_one_card() -> Document:
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="old", color_slot="slot_yellow", tags=["a"]))
    return document


def test_edit_card_text_command_undo_redo():
    document = _document_with_one_card()
    stack = QUndoStack()

    stack.push(EditCardTextCommand(document, "c_1", "old", "new"))
    assert document.get_card("c_1").text == "new"

    stack.undo()
    assert document.get_card("c_1").text == "old"

    stack.redo()
    assert document.get_card("c_1").text == "new"


def test_change_color_command_undo_redo():
    document = _document_with_one_card()
    stack = QUndoStack()

    stack.push(ChangeColorCommand(document, "c_1", "slot_yellow", "slot_blue"))
    assert document.get_card("c_1").color_slot == "slot_blue"

    stack.undo()
    assert document.get_card("c_1").color_slot == "slot_yellow"


def test_change_tags_command_undo_redo():
    document = _document_with_one_card()
    stack = QUndoStack()

    stack.push(ChangeTagsCommand(document, "c_1", ["a"], ["a", "b"]))
    assert document.get_card("c_1").tags == ["a", "b"]

    stack.undo()
    assert document.get_card("c_1").tags == ["a"]

    stack.redo()
    assert document.get_card("c_1").tags == ["a", "b"]


def test_toggle_pin_command_pins_multiple_cards_undo_redo():
    document = Document(name="Test")
    document.add_card(Card(id="c_1"))
    document.add_card(Card(id="c_2"))
    stack = QUndoStack()

    stack.push(TogglePinCommand(document, ["c_1", "c_2"], True))
    assert document.get_card("c_1").pinned is True
    assert document.get_card("c_2").pinned is True

    stack.undo()
    assert document.get_card("c_1").pinned is False
    assert document.get_card("c_2").pinned is False

    stack.redo()
    assert document.get_card("c_1").pinned is True
    assert document.get_card("c_2").pinned is True


def test_toggle_pin_command_undo_restores_mixed_prior_states():
    document = Document(name="Test")
    document.add_card(Card(id="c_1", pinned=True))
    document.add_card(Card(id="c_2", pinned=False))
    stack = QUndoStack()

    # A mixed selection subject to the command pins everyone...
    stack.push(TogglePinCommand(document, ["c_1", "c_2"], True))
    assert document.get_card("c_1").pinned is True
    assert document.get_card("c_2").pinned is True

    # ...but undo must restore each card's own original state, not just
    # flip everyone back to unpinned.
    stack.undo()
    assert document.get_card("c_1").pinned is True
    assert document.get_card("c_2").pinned is False


def test_toggle_pin_command_can_unpin():
    document = Document(name="Test")
    document.add_card(Card(id="c_1", pinned=True))
    stack = QUndoStack()

    stack.push(TogglePinCommand(document, ["c_1"], False))

    assert document.get_card("c_1").pinned is False


def test_move_card_command_undo_redo():
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    stack = QUndoStack()

    stack.push(MoveCardCommand(document, "c_1", (0.0, 0.0), (150.0, 250.0)))
    assert (document.get_card("c_1").x, document.get_card("c_1").y) == (150.0, 250.0)

    stack.undo()
    assert (document.get_card("c_1").x, document.get_card("c_1").y) == (0.0, 0.0)

    stack.redo()
    assert (document.get_card("c_1").x, document.get_card("c_1").y) == (150.0, 250.0)


def test_add_card_command_undo_redo():
    document = Document(name="Test")
    stack = QUndoStack()
    card = Card(id="c_new", text="fresh")

    stack.push(AddCardCommand(document, card))
    assert "c_new" in document.cards

    stack.undo()
    assert "c_new" not in document.cards

    stack.redo()
    assert document.get_card("c_new").text == "fresh"


def test_delete_card_command_restores_card_and_cascaded_links():
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="one"))
    document.add_card(Card(id="c_2", text="two"))
    document.add_card(Card(id="c_3", text="three"))
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    document.add_link(Link(id="l_2", source="c_2", target="c_3"))
    stack = QUndoStack()

    stack.push(DeleteCardCommand(document, "c_1"))
    assert "c_1" not in document.cards
    assert "l_1" not in document.links
    assert "l_2" in document.links

    stack.undo()
    assert document.get_card("c_1").text == "one"
    assert document.get_link("l_1").source == "c_1"
    assert document.get_link("l_1").target == "c_2"


def test_delete_card_with_two_incident_links_removes_and_restores_both():
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="one"))
    document.add_card(Card(id="c_2", text="two"))
    document.add_card(Card(id="c_3", text="three"))
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    document.add_link(Link(id="l_2", source="c_2", target="c_3"))
    stack = QUndoStack()

    stack.push(DeleteCardCommand(document, "c_2"))
    assert "c_2" not in document.cards
    assert document.links == {}

    stack.undo()
    assert document.get_card("c_2").text == "two"
    assert set(document.links) == {"l_1", "l_2"}
    assert document.get_link("l_1").source == "c_1"
    assert document.get_link("l_1").target == "c_2"
    assert document.get_link("l_2").source == "c_2"
    assert document.get_link("l_2").target == "c_3"


def test_delete_card_command_undo_restores_original_position():
    document = Document(name="Test")
    document.add_card(Card(id="c_1"))
    document.add_card(Card(id="c_2"))
    document.add_card(Card(id="c_3"))
    stack = QUndoStack()

    stack.push(DeleteCardCommand(document, "c_2"))
    assert list(document.cards) == ["c_1", "c_3"]

    stack.undo()
    assert list(document.cards) == ["c_1", "c_2", "c_3"]


def test_delete_card_command_macro_for_linked_pair_undoes_cleanly():
    document = Document(name="Test")
    document.add_card(Card(id="c_1"))
    document.add_card(Card(id="c_2"))
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    stack = QUndoStack()

    stack.beginMacro("Delete Cards")
    stack.push(DeleteCardCommand(document, "c_1"))
    stack.push(DeleteCardCommand(document, "c_2"))
    stack.endMacro()

    assert document.cards == {}
    assert document.links == {}

    stack.undo()

    assert set(document.cards) == {"c_1", "c_2"}
    assert set(document.links) == {"l_1"}
    assert document.get_link("l_1").source == "c_1"
    assert document.get_link("l_1").target == "c_2"


def test_add_link_command_undo_redo():
    document = Document(name="Test")
    document.add_card(Card(id="c_1"))
    document.add_card(Card(id="c_2"))
    stack = QUndoStack()
    link = Link(id="l_1", source="c_1", target="c_2")

    stack.push(AddLinkCommand(document, link))
    assert "l_1" in document.links

    stack.undo()
    assert "l_1" not in document.links

    stack.redo()
    assert document.get_link("l_1").source == "c_1"
    assert document.get_link("l_1").target == "c_2"


def test_delete_link_command_undo_redo():
    document = Document(name="Test")
    document.add_card(Card(id="c_1"))
    document.add_card(Card(id="c_2"))
    document.add_link(Link(id="l_1", source="c_1", target="c_2", label="relates"))
    stack = QUndoStack()

    stack.push(DeleteLinkCommand(document, "l_1"))
    assert "l_1" not in document.links

    stack.undo()
    assert document.get_link("l_1").source == "c_1"
    assert document.get_link("l_1").target == "c_2"
    assert document.get_link("l_1").label == "relates"


def test_auto_arrange_command_undo_redo_restores_exact_prior_layout():
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=5.0, y=10.0))
    document.add_card(Card(id="c_2", x=600.0, y=700.0))
    document.add_card(Card(id="c_3", x=42.0, y=99.0))
    stack = QUndoStack()

    old_positions = {
        card.id: (card.x, card.y) for card in document.iter_cards()
    }
    new_positions = {"c_1": (0.0, 0.0), "c_2": (24.0, 24.0), "c_3": (220.0, 0.0)}

    stack.push(AutoArrangeCommand(document, old_positions, new_positions))
    assert (document.get_card("c_1").x, document.get_card("c_1").y) == (0.0, 0.0)
    assert (document.get_card("c_2").x, document.get_card("c_2").y) == (24.0, 24.0)
    assert (document.get_card("c_3").x, document.get_card("c_3").y) == (220.0, 0.0)

    stack.undo()
    assert (document.get_card("c_1").x, document.get_card("c_1").y) == (5.0, 10.0)
    assert (document.get_card("c_2").x, document.get_card("c_2").y) == (600.0, 700.0)
    assert (document.get_card("c_3").x, document.get_card("c_3").y) == (42.0, 99.0)

    stack.redo()
    assert (document.get_card("c_1").x, document.get_card("c_1").y) == (0.0, 0.0)


def test_change_canvas_background_command_undo_redo():
    document = Document(name="Test")
    original_color = document.canvas_background_color
    stack = QUndoStack()

    stack.push(ChangeCanvasBackgroundCommand(document, original_color, "#123456"))
    assert document.canvas_background_color == "#123456"

    stack.undo()
    assert document.canvas_background_color == original_color

    stack.redo()
    assert document.canvas_background_color == "#123456"


def test_move_cards_command_undo_redo():
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0))
    document.add_card(Card(id="c_2", x=10.0, y=10.0))
    stack = QUndoStack()

    old_positions = {"c_1": (0.0, 0.0), "c_2": (10.0, 10.0)}
    new_positions = {"c_1": (100.0, 100.0), "c_2": (110.0, 110.0)}
    stack.push(MoveCardsCommand(document, old_positions, new_positions))
    assert (document.get_card("c_1").x, document.get_card("c_1").y) == (100.0, 100.0)
    assert (document.get_card("c_2").x, document.get_card("c_2").y) == (110.0, 110.0)

    stack.undo()
    assert (document.get_card("c_1").x, document.get_card("c_1").y) == (0.0, 0.0)
    assert (document.get_card("c_2").x, document.get_card("c_2").y) == (10.0, 10.0)


def test_move_stack_command_undo_redo():
    document = Document(name="Test")
    document.add_stack(Stack(id="s_1", x=0.0, y=0.0))
    stack = QUndoStack()

    stack.push(MoveStackCommand(document, "s_1", (0.0, 0.0), (150.0, 250.0)))
    assert (document.get_stack("s_1").x, document.get_stack("s_1").y) == (150.0, 250.0)

    stack.undo()
    assert (document.get_stack("s_1").x, document.get_stack("s_1").y) == (0.0, 0.0)

    stack.redo()
    assert (document.get_stack("s_1").x, document.get_stack("s_1").y) == (150.0, 250.0)


def test_create_stack_command_undo_redo():
    document = Document(name="Test")
    document.add_card(Card(id="c_1", pinned=True))
    document.add_card(Card(id="c_2"))
    undo_stack = QUndoStack()
    new_stack = Stack(id="s_1", x=5.0, y=5.0, label="Chapter 1")

    undo_stack.push(CreateStackCommand(document, new_stack, ["c_1", "c_2"]))
    assert document.get_card("c_1").stack_id == "s_1"
    assert document.get_card("c_1").pinned is False  # joining a stack unpins
    assert document.get_stack("s_1").card_ids == ["c_1", "c_2"]

    undo_stack.undo()
    assert "s_1" not in document.stacks
    assert document.get_card("c_1").stack_id is None
    assert document.get_card("c_1").pinned is True  # restored
    assert document.get_card("c_2").stack_id is None

    undo_stack.redo()
    assert document.get_stack("s_1").card_ids == ["c_1", "c_2"]


def test_add_cards_to_stack_command_undo_redo():
    document = Document(name="Test")
    document.add_card(Card(id="c_1"))
    document.add_stack(Stack(id="s_1"))
    undo_stack = QUndoStack()

    undo_stack.push(AddCardsToStackCommand(document, "s_1", ["c_1"]))
    assert document.get_card("c_1").stack_id == "s_1"
    assert document.get_stack("s_1").card_ids == ["c_1"]

    undo_stack.undo()
    assert document.get_card("c_1").stack_id is None
    assert document.get_stack("s_1").card_ids == []


def test_remove_stack_command_undo_restores_original_position():
    document = Document(name="Test")
    document.add_stack(Stack(id="s_1"))
    document.add_stack(Stack(id="s_2"))
    document.add_stack(Stack(id="s_3"))
    undo_stack = QUndoStack()

    undo_stack.push(RemoveStackCommand(document, "s_2"))
    assert list(document.stacks) == ["s_1", "s_3"]

    undo_stack.undo()
    assert list(document.stacks) == ["s_1", "s_2", "s_3"]


def test_explode_stack_command_undo_redo_restores_membership_and_positions():
    document = Document(name="Test")
    document.add_card(Card(id="c_1", x=0.0, y=0.0, stack_id="s_1"))
    document.add_card(Card(id="c_2", x=0.0, y=0.0, stack_id="s_1"))
    document.add_stack(Stack(id="s_1", card_ids=["c_1", "c_2"], x=5.0, y=5.0))
    undo_stack = QUndoStack()

    new_positions = {"c_1": (100.0, 100.0), "c_2": (300.0, 100.0)}
    undo_stack.push(ExplodeStackCommand(document, "s_1", new_positions))
    assert "s_1" not in document.stacks
    assert document.get_card("c_1").stack_id is None
    assert (document.get_card("c_1").x, document.get_card("c_1").y) == (100.0, 100.0)
    assert (document.get_card("c_2").x, document.get_card("c_2").y) == (300.0, 100.0)

    undo_stack.undo()
    assert document.get_card("c_1").stack_id == "s_1"
    assert document.get_card("c_2").stack_id == "s_1"
    assert (document.get_card("c_1").x, document.get_card("c_1").y) == (0.0, 0.0)
    # Regression: the restored stack must not come back with an empty
    # card_ids list (remove_cards_from_stack mutates the Stack object in
    # place before it's returned by remove_stack).
    assert document.get_stack("s_1").card_ids == ["c_1", "c_2"]

    undo_stack.redo()
    assert "s_1" not in document.stacks
    assert (document.get_card("c_1").x, document.get_card("c_1").y) == (100.0, 100.0)


def test_change_stack_label_command_undo_redo():
    document = Document(name="Test")
    document.add_stack(Stack(id="s_1", label="old"))
    stack = QUndoStack()

    stack.push(ChangeStackLabelCommand(document, "s_1", "old", "new"))
    assert document.get_stack("s_1").label == "new"

    stack.undo()
    assert document.get_stack("s_1").label == "old"


def test_gather_stacks_command_undo_redo():
    document = Document(name="Test")
    document.add_stack(Stack(id="s_1", x=0.0, y=0.0))
    document.add_stack(Stack(id="s_2", x=500.0, y=500.0))
    undo_stack = QUndoStack()

    old_positions = {"s_1": (0.0, 0.0), "s_2": (500.0, 500.0)}
    new_positions = {"s_1": (0.0, 0.0), "s_2": (220.0, 0.0)}
    undo_stack.push(GatherStacksCommand(document, old_positions, new_positions))
    assert (document.get_stack("s_2").x, document.get_stack("s_2").y) == (220.0, 0.0)

    undo_stack.undo()
    assert (document.get_stack("s_2").x, document.get_stack("s_2").y) == (500.0, 500.0)


def test_push_delete_stack_and_cards_removes_stack_and_all_members():
    document = Document(name="Test")
    document.add_card(Card(id="c_1", stack_id="s_1"))
    document.add_card(Card(id="c_2", stack_id="s_1"))
    document.add_link(Link(id="l_1", source="c_1", target="c_2"))
    document.add_stack(Stack(id="s_1", card_ids=["c_1", "c_2"]))
    undo_stack = QUndoStack()

    push_delete_stack_and_cards(undo_stack, document, "s_1")
    assert "s_1" not in document.stacks
    assert document.cards == {}
    assert document.links == {}

    undo_stack.undo()
    assert set(document.cards) == {"c_1", "c_2"}
    assert document.get_stack("s_1").card_ids == ["c_1", "c_2"]
    assert set(document.links) == {"l_1"}
