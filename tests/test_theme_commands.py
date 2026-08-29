from PySide6.QtGui import QUndoStack

from indexcards.commands.theme_commands import SetDocumentThemeCommand
from indexcards.models.document import Document
from indexcards.models.theme import Theme


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
