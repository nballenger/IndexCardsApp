from PySide6.QtWidgets import QMessageBox

from indexcards.widgets import dialogs


def test_confirm_delete_cards_message_mentions_link_cascade(qtbot, monkeypatch):
    seen_messages = []

    def fake_question(parent, title, message, buttons, default):
        seen_messages.append(message)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", staticmethod(fake_question))

    result = dialogs.confirm_delete_cards(None, card_count=2, incident_link_count=3)

    assert result is True
    assert "2 cards" in seen_messages[0]
    assert "3 connected links" in seen_messages[0]


def test_confirm_delete_cards_singular_wording(qtbot, monkeypatch):
    seen_messages = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(
            lambda parent, title, message, buttons, default: seen_messages.append(message)
            or QMessageBox.StandardButton.Yes
        ),
    )

    dialogs.confirm_delete_cards(None, card_count=1, incident_link_count=1)

    assert "1 card?" in seen_messages[0]
    assert "1 connected link." in seen_messages[0]


def test_confirm_delete_cards_no_links_omits_cascade_sentence(qtbot, monkeypatch):
    seen_messages = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(
            lambda parent, title, message, buttons, default: seen_messages.append(message)
            or QMessageBox.StandardButton.Yes
        ),
    )

    dialogs.confirm_delete_cards(None, card_count=1, incident_link_count=0)

    assert seen_messages[0] == "Delete 1 card?"


def test_confirm_delete_cards_returns_false_on_no(qtbot, monkeypatch):
    monkeypatch.setattr(
        QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.No)
    )

    assert dialogs.confirm_delete_cards(None, card_count=1, incident_link_count=0) is False
