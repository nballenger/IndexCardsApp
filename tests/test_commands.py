from PySide6.QtGui import QUndoStack

from indexcards.commands.card_commands import (
    ChangeColorCommand,
    ChangeTagsCommand,
    EditCardTextCommand,
)
from indexcards.models.card import Card
from indexcards.models.document import Document


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
