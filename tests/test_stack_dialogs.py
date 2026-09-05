from PySide6.QtWidgets import QDialogButtonBox, QMessageBox

from indexcards.widgets import stack_dialogs


def test_confirm_delete_stack_message_with_label(qtbot, monkeypatch):
    seen_messages = []

    def fake_exec(self):
        seen_messages.append(self.text())
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)

    result = stack_dialogs.confirm_delete_stack(None, "Chapter 1", 3)

    assert result is True
    assert seen_messages[0] == 'Delete stack "Chapter 1"? Doing so will also delete 3 cards.'


def test_confirm_delete_stack_message_without_label(monkeypatch):
    seen_messages = []

    def fake_exec(self):
        seen_messages.append(self.text())
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)

    stack_dialogs.confirm_delete_stack(None, "", 1)

    assert seen_messages[0] == "Delete stack? Doing so will also delete 1 card."


def test_confirm_delete_stack_returns_false_on_cancel(monkeypatch):
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.Cancel)

    result = stack_dialogs.confirm_delete_stack(None, "Chapter 1", 2)

    assert result is False


def test_confirm_delete_stack_relabels_affirmative_button(monkeypatch):
    seen_labels = []

    def fake_exec(self):
        seen_labels.append(self.button(QMessageBox.StandardButton.Yes).text())
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)

    stack_dialogs.confirm_delete_stack(None, "Chapter 1", 2)

    assert seen_labels == ["Delete Stack and Cards"]


def test_confirm_add_all_to_stack_message_with_label(monkeypatch):
    seen_messages = []

    def fake_exec(self):
        seen_messages.append(self.text())
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)

    result = stack_dialogs.confirm_add_all_to_stack(None, "Chapter 1")

    assert result is True
    assert seen_messages[0] == 'Add all to stack "Chapter 1"?'


def test_confirm_add_all_to_stack_message_without_label(monkeypatch):
    seen_messages = []

    def fake_exec(self):
        seen_messages.append(self.text())
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)

    stack_dialogs.confirm_add_all_to_stack(None, "")

    assert seen_messages[0] == "Add all to stack?"


def test_confirm_add_all_to_stack_returns_false_on_cancel(monkeypatch):
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.Cancel)

    result = stack_dialogs.confirm_add_all_to_stack(None, "Chapter 1")

    assert result is False


def test_create_stack_prompt_dialog_label_defaults_empty(qtbot):
    dialog = stack_dialogs.CreateStackPromptDialog("Create a stack containing both cards?")
    qtbot.addWidget(dialog)

    assert dialog.label() == ""


def test_create_stack_prompt_dialog_returns_typed_label(qtbot):
    dialog = stack_dialogs.CreateStackPromptDialog("Create a stack containing both cards?")
    qtbot.addWidget(dialog)

    dialog.label_edit.setText("  Chapter 1  ")

    assert dialog.label() == "Chapter 1"


def test_create_stack_prompt_dialog_has_ok_and_cancel_buttons(qtbot):
    dialog = stack_dialogs.CreateStackPromptDialog("Create a stack containing both cards?")
    qtbot.addWidget(dialog)

    button_box = dialog.findChild(QDialogButtonBox)
    assert button_box.button(QDialogButtonBox.StandardButton.Ok) is not None
    assert button_box.button(QDialogButtonBox.StandardButton.Cancel) is not None


def test_create_stack_prompt_dialog_title_defaults_to_create_stack(qtbot):
    dialog = stack_dialogs.CreateStackPromptDialog("Create a stack containing both cards?")
    qtbot.addWidget(dialog)

    assert dialog.windowTitle() == "Create Stack"


def test_create_stack_prompt_dialog_title_is_configurable(qtbot):
    dialog = stack_dialogs.CreateStackPromptDialog(
        "Merge these two stacks?", title="Merge Stacks"
    )
    qtbot.addWidget(dialog)

    assert dialog.windowTitle() == "Merge Stacks"
