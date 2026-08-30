from PySide6.QtGui import QUndoStack

from indexcards.commands.theme_commands import (
    KeepOrphanColorCommand,
    ReassignOrphanColorCommand,
    SetDocumentThemeCommand,
)
from indexcards.models.card import Card
from indexcards.models.document import Document
from indexcards.models.theme import Slot, Theme


def test_set_document_theme_command_undo_redo():
    old_theme = Theme(id="t_1", name="Old", origin="custom", background_color="#111111")
    new_theme = Theme(id="t_2", name="New", origin="custom", background_color="#222222")
    document = Document(name="Test", theme=old_theme)
    stack = QUndoStack()

    stack.push(SetDocumentThemeCommand(document, old_theme, new_theme))
    assert document.theme is new_theme

    stack.undo()
    assert document.theme is old_theme

    stack.redo()
    assert document.theme is new_theme


def test_set_document_theme_command_marks_dirty_on_redo():
    old_theme = Theme(id="t_1", name="Old", origin="custom", background_color="#111111")
    new_theme = Theme(id="t_2", name="New", origin="custom", background_color="#222222")
    document = Document(name="Test", theme=old_theme)
    document.mark_clean()
    stack = QUndoStack()

    stack.push(SetDocumentThemeCommand(document, old_theme, new_theme))

    assert document.dirty is True


def test_set_document_theme_command_with_remap_rewrites_cards_on_redo_and_undo():
    old_theme = Theme(
        id="t_1", name="Old", origin="custom", background_color="#111111",
        slots=[Slot(id="slot_a", label="A", hex="#ff0000")],
    )
    new_theme = Theme(
        id="t_2", name="New", origin="custom", background_color="#222222",
        slots=[Slot(id="other_x", label="X", hex="#00ff00")],
    )
    document = Document(name="Test", theme=old_theme)
    document.add_card(Card(id="c_1", color_slot="slot_a"))
    stack = QUndoStack()

    stack.push(SetDocumentThemeCommand(document, old_theme, new_theme, {"slot_a": "other_x"}))
    assert document.theme is new_theme
    assert document.get_card("c_1").color_slot == "other_x"

    stack.undo()
    assert document.theme is old_theme
    assert document.get_card("c_1").color_slot == "slot_a"

    stack.redo()
    assert document.theme is new_theme
    assert document.get_card("c_1").color_slot == "other_x"


def _document_with_orphan_theme() -> Document:
    theme = Theme(
        id="t_1",
        name="Test",
        origin="custom",
        background_color="#3d6b4f",
        slots=[
            Slot(id="slot_a", label="A", hex="#ff0000"),
            Slot(id="slot_b", label="B", hex="#00ff00", orphaned=True),
        ],
    )
    document = Document(name="Test", theme=theme)
    document.add_card(Card(id="c_1", color_slot="slot_b"))
    return document


def test_keep_orphan_color_command_undo_redo():
    document = _document_with_orphan_theme()
    stack = QUndoStack()

    stack.push(KeepOrphanColorCommand(document, "slot_b"))
    assert document.get_slot("slot_b").orphaned is False

    stack.undo()
    assert document.get_slot("slot_b").orphaned is True

    stack.redo()
    assert document.get_slot("slot_b").orphaned is False


def test_reassign_orphan_color_command_undo_redo():
    document = _document_with_orphan_theme()
    stack = QUndoStack()

    stack.push(ReassignOrphanColorCommand(document, "slot_b", "slot_a"))
    assert document.get_card("c_1").color_slot == "slot_a"
    assert document.theme.get_slot("slot_b") is None

    stack.undo()
    assert document.get_card("c_1").color_slot == "slot_b"
    restored = document.theme.get_slot("slot_b")
    assert restored is not None
    assert restored.hex == "#00ff00"
    assert [slot.id for slot in document.theme.slots] == ["slot_a", "slot_b"]

    stack.redo()
    assert document.get_card("c_1").color_slot == "slot_a"
    assert document.theme.get_slot("slot_b") is None


def test_reassign_orphan_color_command_undo_restores_multiple_affected_cards():
    document = _document_with_orphan_theme()
    document.add_card(Card(id="c_2", color_slot="slot_b"))
    stack = QUndoStack()

    stack.push(ReassignOrphanColorCommand(document, "slot_b", "slot_a"))
    stack.undo()

    assert document.get_card("c_1").color_slot == "slot_b"
    assert document.get_card("c_2").color_slot == "slot_b"
