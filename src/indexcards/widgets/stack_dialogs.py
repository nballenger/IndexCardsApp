from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)


def confirm_delete_stack(parent: QWidget, stack_label: str, card_count: int) -> bool:
    """Asks the user to confirm deleting a stack and all its member cards.

    Uses relabeled standard buttons (rather than addButton(..., role) +
    clickedButton() comparisons) so this stays testable the same way
    confirm_delete_cards is: monkeypatching QMessageBox.exec directly.
    """
    label_suffix = f' "{stack_label}"' if stack_label else ""
    plural = "s" if card_count != 1 else ""
    message = f"Delete stack{label_suffix}? Doing so will also delete {card_count} card{plural}."

    box = QMessageBox(parent)
    box.setWindowTitle("Delete Stack")
    box.setIcon(QMessageBox.Icon.Question)
    box.setText(message)
    box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
    box.button(QMessageBox.StandardButton.Yes).setText("Delete Stack and Cards")
    box.setDefaultButton(QMessageBox.StandardButton.Cancel)

    return box.exec() == QMessageBox.StandardButton.Yes


def confirm_add_all_to_stack(parent: QWidget, stack_label: str) -> bool:
    """Asks whether to add every card in a multi-card drag to the stack
    dropped onto. Same relabeled-standard-button pattern as
    confirm_delete_stack, for the same testability reason."""
    message = f'Add all to stack "{stack_label}"?' if stack_label else "Add all to stack?"

    box = QMessageBox(parent)
    box.setWindowTitle("Add to Stack")
    box.setIcon(QMessageBox.Icon.Question)
    box.setText(message)
    box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
    box.button(QMessageBox.StandardButton.Yes).setText("Add All")
    box.setDefaultButton(QMessageBox.StandardButton.Cancel)

    return box.exec() == QMessageBox.StandardButton.Yes


def prompt_optional_stack_label(parent: QWidget, title: str = "Label Stack") -> str:
    """Menu-driven "New Stack..." flow: the stack is already going to be
    created regardless of this dialog's outcome, so both Cancel and a
    blank entry simply mean "no label" — matching the existing
    CardItem._edit_tags_via_dialog idiom."""
    text, _ok = QInputDialog.getText(parent, title, "Label (optional):")
    return text.strip()


class CreateStackPromptDialog(QDialog):
    """Confirms creating a new stack from a drag-onto-card gesture, with an
    optional label. Unlike prompt_optional_stack_label (used when creation
    is already decided), Cancel here must mean "don't create a stack at
    all" — a plain QInputDialog can't distinguish that from "create with a
    blank label," so this is a real QDialog instead."""

    def __init__(
        self, message: str, parent: QWidget | None = None, title: str = "Create Stack"
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)

        self.label_edit = QLineEdit(self)
        self.label_edit.setPlaceholderText("Label (optional)")

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(message, self))
        layout.addWidget(self.label_edit)
        layout.addWidget(button_box)

    def label(self) -> str:
        return self.label_edit.text().strip()
