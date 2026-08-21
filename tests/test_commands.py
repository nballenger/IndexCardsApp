from PySide6.QtGui import QUndoStack

from indexcards.commands.card_commands import (
    AddCardCommand,
    ChangeColorCommand,
    ChangeTagsCommand,
    DeleteCardCommand,
    EditCardTextCommand,
)
from indexcards.commands.move_commands import MoveCardCommand
from indexcards.models.card import Card
from indexcards.models.document import Document
from indexcards.models.link import Link


def _document_with_one_card() -> Document:
    document = Document(name="Test")
    document.add_card(Card(id="c_1", text="old", color="#F6E27A", tags=["a"]))
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

    stack.push(ChangeColorCommand(document, "c_1", "#F6E27A", "#A8D8F0"))
    assert document.get_card("c_1").color == "#A8D8F0"

    stack.undo()
    assert document.get_card("c_1").color == "#F6E27A"


def test_change_tags_command_undo_redo():
    document = _document_with_one_card()
    stack = QUndoStack()

    stack.push(ChangeTagsCommand(document, "c_1", ["a"], ["a", "b"]))
    assert document.get_card("c_1").tags == ["a", "b"]

    stack.undo()
    assert document.get_card("c_1").tags == ["a"]

    stack.redo()
    assert document.get_card("c_1").tags == ["a", "b"]


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
