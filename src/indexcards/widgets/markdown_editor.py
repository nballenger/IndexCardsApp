from __future__ import annotations

from PySide6.QtGui import QFont, QKeySequence, QShortcut, QTextCharFormat, QUndoStack
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from indexcards.commands.card_commands import (
    ChangeColorCommand,
    ChangeTagsCommand,
    EditCardTextCommand,
)
from indexcards.models.document import Document
from indexcards.models.palette import PALETTE


class _EditorTextEdit(QTextEdit):
    """QTextEdit that reports focus loss, so edits commit on focus-out."""

    def __init__(self, on_focus_out, parent=None) -> None:
        super().__init__(parent)
        self._on_focus_out = on_focus_out

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self._on_focus_out()


class MarkdownEditorWidget(QWidget):
    """Shared card editor reflecting whichever card is selected in either
    view: markdown text on top, tags/color metadata below.

    Text edits commit on focus-out (not per keystroke) as an
    EditCardTextCommand, the same command list-view cell editing already
    uses, so both surfaces share one undo history and stay in sync via
    Document.cardChanged. Tags commit on Enter/focus-out (QLineEdit's
    editingFinished); color commits immediately on selection, same as the
    list view's color delegate.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._document: Document | None = None
        self._undo_stack: QUndoStack | None = None
        self._card_id: str | None = None
        self._loading_metadata = False

        self.text_edit = _EditorTextEdit(self._commit, self)
        self.text_edit.setEnabled(False)

        self.bold_button = QPushButton("B", self)
        self.bold_button.setToolTip("Bold (Cmd+B)")
        self.bold_button.clicked.connect(self._toggle_bold)

        self.italic_button = QPushButton("I", self)
        self.italic_button.setToolTip("Italic (Cmd+I)")
        self.italic_button.clicked.connect(self._toggle_italic)

        for button in (self.bold_button, self.italic_button):
            button.setFixedWidth(28)
            button.setEnabled(False)

        toolbar_layout = QHBoxLayout()
        toolbar_layout.addWidget(self.bold_button)
        toolbar_layout.addWidget(self.italic_button)
        toolbar_layout.addStretch()

        self.tags_edit = QLineEdit(self)
        self.tags_edit.setPlaceholderText("Tags (comma-separated)")
        self.tags_edit.editingFinished.connect(self._commit_tags)
        self.tags_edit.setEnabled(False)

        self.color_combo = QComboBox(self)
        for name, hex_value in PALETTE.items():
            self.color_combo.addItem(name, hex_value)
        self.color_combo.currentIndexChanged.connect(self._commit_color)
        self.color_combo.setEnabled(False)

        metadata_layout = QHBoxLayout()
        metadata_layout.addWidget(QLabel("Tags:", self))
        metadata_layout.addWidget(self.tags_edit, stretch=1)
        metadata_layout.addWidget(QLabel("Color:", self))
        metadata_layout.addWidget(self.color_combo)

        layout = QVBoxLayout(self)
        layout.addLayout(toolbar_layout)
        layout.addWidget(self.text_edit)
        layout.addLayout(metadata_layout)

        QShortcut(QKeySequence.StandardKey.Bold, self.text_edit).activated.connect(
            self._toggle_bold
        )
        QShortcut(QKeySequence.StandardKey.Italic, self.text_edit).activated.connect(
            self._toggle_italic
        )

    def set_card(
        self, document: Document | None, undo_stack: QUndoStack | None, card_id: str | None
    ) -> None:
        self._commit()
        self._commit_tags()

        if document is not self._document:
            if self._document is not None:
                self._document.cardChanged.disconnect(self._on_document_card_changed)
                self._document.cardRemoved.disconnect(self._on_document_card_removed)
            if document is not None:
                document.cardChanged.connect(self._on_document_card_changed)
                document.cardRemoved.connect(self._on_document_card_removed)

        self._document = document
        self._undo_stack = undo_stack
        self._card_id = card_id
        self._load_current_card()

    def _load_current_card(self) -> None:
        enabled = self._document is not None and self._card_id is not None
        if not enabled:
            self.text_edit.clear()
            self.tags_edit.clear()
        else:
            self._load_text()
            self._load_tags()
            self._load_color()

        self.text_edit.setEnabled(enabled)
        self.tags_edit.setEnabled(enabled)
        self.color_combo.setEnabled(enabled)
        self.bold_button.setEnabled(enabled)
        self.italic_button.setEnabled(enabled)

    def _load_text(self) -> None:
        card = self._document.get_card(self._card_id)
        self.text_edit.document().setMarkdown(card.text)
        self.text_edit.document().setModified(False)

    def _load_tags(self) -> None:
        card = self._document.get_card(self._card_id)
        self.tags_edit.setText(", ".join(card.tags))
        self.tags_edit.setModified(False)

    def _load_color(self) -> None:
        card = self._document.get_card(self._card_id)
        self._loading_metadata = True
        try:
            position = self.color_combo.findData(card.color)
            self.color_combo.setCurrentIndex(position if position >= 0 else 0)
        finally:
            self._loading_metadata = False

    def _commit(self) -> None:
        if self._document is None or self._card_id is None:
            return
        if not self.text_edit.document().isModified():
            return

        new_text = self.text_edit.document().toMarkdown()
        old_text = self._document.get_card(self._card_id).text
        if new_text != old_text:
            command = EditCardTextCommand(self._document, self._card_id, old_text, new_text)
            if self._undo_stack is not None:
                self._undo_stack.push(command)
            else:
                self._document.set_card_text(self._card_id, new_text)
        self.text_edit.document().setModified(False)

    def _commit_tags(self) -> None:
        if self._document is None or self._card_id is None:
            return
        if not self.tags_edit.isModified():
            return
        new_tags = [tag.strip() for tag in self.tags_edit.text().split(",") if tag.strip()]
        old_tags = self._document.get_card(self._card_id).tags
        if new_tags != old_tags:
            command = ChangeTagsCommand(self._document, self._card_id, old_tags, new_tags)
            if self._undo_stack is not None:
                self._undo_stack.push(command)
            else:
                self._document.set_card_tags(self._card_id, new_tags)
        self.tags_edit.setModified(False)

    def _commit_color(self, _index: int) -> None:
        if self._loading_metadata or self._document is None or self._card_id is None:
            return
        new_color = self.color_combo.currentData()
        old_color = self._document.get_card(self._card_id).color
        if new_color == old_color:
            return
        command = ChangeColorCommand(self._document, self._card_id, old_color, new_color)
        if self._undo_stack is not None:
            self._undo_stack.push(command)
        else:
            self._document.set_card_color(self._card_id, new_color)

    def _toggle_bold(self) -> None:
        if not self.text_edit.isEnabled():
            return
        fmt = QTextCharFormat()
        is_bold = self.text_edit.fontWeight() == QFont.Weight.Bold
        fmt.setFontWeight(QFont.Weight.Normal if is_bold else QFont.Weight.Bold)
        self.text_edit.mergeCurrentCharFormat(fmt)
        self.text_edit.setFocus()

    def _toggle_italic(self) -> None:
        if not self.text_edit.isEnabled():
            return
        fmt = QTextCharFormat()
        fmt.setFontItalic(not self.text_edit.fontItalic())
        self.text_edit.mergeCurrentCharFormat(fmt)
        self.text_edit.setFocus()

    def _on_document_card_changed(self, card_id: str, fields: frozenset[str]) -> None:
        if card_id != self._card_id:
            return
        if "text" in fields and not (
            self.text_edit.hasFocus() or self.text_edit.document().isModified()
        ):
            self._load_text()
        if "tags" in fields and not self.tags_edit.hasFocus():
            self._load_tags()
        if "color" in fields:
            self._load_color()

    def _on_document_card_removed(self, card_id: str) -> None:
        if card_id != self._card_id:
            return
        self._card_id = None
        self._load_current_card()
