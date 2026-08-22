from PySide6.QtWidgets import QMessageBox

from indexcards.app_settings import AppSettings
from indexcards.widgets import dialogs


def test_confirm_delete_cards_message_mentions_link_cascade(qtbot, monkeypatch):
    seen_messages = []

    def fake_exec(self):
        seen_messages.append(self.text())
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)

    result = dialogs.confirm_delete_cards(
        None, card_count=2, incident_link_count=3, settings=AppSettings()
    )

    assert result is True
    assert "2 cards" in seen_messages[0]
    assert "3 connected links" in seen_messages[0]


def test_confirm_delete_cards_singular_wording(qtbot, monkeypatch):
    seen_messages = []

    def fake_exec(self):
        seen_messages.append(self.text())
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)

    dialogs.confirm_delete_cards(None, card_count=1, incident_link_count=1, settings=AppSettings())

    assert "1 card?" in seen_messages[0]
    assert "1 connected link." in seen_messages[0]


def test_confirm_delete_cards_no_links_omits_cascade_sentence(qtbot, monkeypatch):
    seen_messages = []

    def fake_exec(self):
        seen_messages.append(self.text())
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)

    dialogs.confirm_delete_cards(None, card_count=1, incident_link_count=0, settings=AppSettings())

    assert seen_messages[0] == "Delete 1 card?"


def test_confirm_delete_cards_returns_false_on_no(qtbot, monkeypatch):
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.No)

    result = dialogs.confirm_delete_cards(
        None, card_count=1, incident_link_count=0, settings=AppSettings()
    )

    assert result is False


def test_confirm_delete_cards_skips_dialog_when_warn_before_delete_is_false(qtbot, monkeypatch):
    def fail_if_called(self):
        raise AssertionError("QMessageBox.exec should not be called")

    monkeypatch.setattr(QMessageBox, "exec", fail_if_called)

    settings = AppSettings()
    settings.warn_before_delete = False

    result = dialogs.confirm_delete_cards(
        None, card_count=1, incident_link_count=0, settings=settings
    )

    assert result is True


def test_confirm_delete_cards_checkbox_default_unchecked(qtbot, monkeypatch):
    seen_checked_states = []

    def fake_exec(self):
        seen_checked_states.append(self.checkBox().isChecked())
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)

    dialogs.confirm_delete_cards(None, card_count=1, incident_link_count=0, settings=AppSettings())

    assert seen_checked_states == [False]


def test_confirm_delete_cards_dont_ask_again_checked_on_yes_disables_setting(qtbot, monkeypatch):
    def fake_exec(self):
        self.checkBox().setChecked(True)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)

    settings = AppSettings()
    result = dialogs.confirm_delete_cards(
        None, card_count=1, incident_link_count=0, settings=settings
    )

    assert result is True
    assert settings.warn_before_delete is False


def test_confirm_delete_cards_dont_ask_again_checked_on_no_still_disables_setting(
    qtbot, monkeypatch
):
    # Locks in the clarified behavior: the checkbox is a standalone
    # preference toggle, independent of whether this specific deletion
    # is confirmed or cancelled.
    def fake_exec(self):
        self.checkBox().setChecked(True)
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)

    settings = AppSettings()
    result = dialogs.confirm_delete_cards(
        None, card_count=1, incident_link_count=0, settings=settings
    )

    assert result is False
    assert settings.warn_before_delete is False


def test_confirm_delete_cards_dont_ask_again_left_unchecked_leaves_setting_untouched(
    qtbot, monkeypatch
):
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.Yes)

    settings = AppSettings()
    dialogs.confirm_delete_cards(None, card_count=1, incident_link_count=0, settings=settings)

    assert settings.warn_before_delete is True
