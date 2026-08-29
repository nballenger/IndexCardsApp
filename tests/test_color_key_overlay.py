from PySide6.QtWidgets import QWidget

from indexcards.canvas.color_key_overlay import ColorKeyOverlay
from indexcards.models.card import Card
from indexcards.models.document import Document


def _document() -> Document:
    return Document(name="Test")


def _overlay(qtbot) -> tuple[ColorKeyOverlay, QWidget]:
    parent = QWidget()
    parent.resize(400, 300)
    qtbot.addWidget(parent)
    parent.show()  # isVisible() reflects ancestor visibility too, not just the overlay's own flag
    overlay = ColorKeyOverlay(parent)
    return overlay, parent


def test_hidden_with_no_document(qtbot):
    overlay, _parent = _overlay(qtbot)
    assert overlay.isVisible() is False


def test_hidden_when_document_color_key_not_visible(qtbot):
    overlay, _parent = _overlay(qtbot)
    document = _document()
    document.add_card(Card(id="c_1"))

    overlay.set_document(document)

    assert overlay.isVisible() is False


def test_visible_when_document_color_key_visible(qtbot):
    overlay, _parent = _overlay(qtbot)
    document = _document()
    document.add_card(Card(id="c_1"))
    document.set_color_key_visible(True)

    overlay.set_document(document)

    assert overlay.isVisible() is True


def test_becomes_visible_live_when_toggled_on(qtbot):
    overlay, _parent = _overlay(qtbot)
    document = _document()
    document.add_card(Card(id="c_1"))
    overlay.set_document(document)
    assert overlay.isVisible() is False

    document.set_color_key_visible(True)

    assert overlay.isVisible() is True


def test_entries_include_only_in_use_slots(qtbot):
    overlay, _parent = _overlay(qtbot)
    document = _document()
    document.add_card(Card(id="c_1", color_slot="slot_white"))
    document.set_color_key_visible(True)
    overlay.set_document(document)

    labels = [slot.label for slot in overlay._entries()]

    assert labels == ["White"]


def test_entries_update_live_when_a_new_card_uses_a_new_color(qtbot):
    overlay, _parent = _overlay(qtbot)
    document = _document()
    document.add_card(Card(id="c_1", color_slot="slot_white"))
    document.set_color_key_visible(True)
    overlay.set_document(document)

    document.add_card(Card(id="c_2", color_slot="slot_blue"))

    labels = {slot.label for slot in overlay._entries()}
    assert labels == {"White", "Blue"}


def test_entries_update_live_when_a_cards_color_changes(qtbot):
    overlay, _parent = _overlay(qtbot)
    document = _document()
    document.add_card(Card(id="c_1", color_slot="slot_white"))
    document.set_color_key_visible(True)
    overlay.set_document(document)

    document.set_card_color_slot("c_1", "slot_blue")

    labels = [slot.label for slot in overlay._entries()]
    assert labels == ["Blue"]


def test_entries_include_orphaned_slots_still_in_use(qtbot):
    overlay, _parent = _overlay(qtbot)
    document = _document()
    document.add_card(Card(id="c_1", color_slot="slot_white"))
    document.theme.slots[0].orphaned = True
    document.set_color_key_visible(True)
    overlay.set_document(document)

    entries = overlay._entries()

    assert len(entries) == 1
    assert entries[0].orphaned is True


def test_entries_orders_active_slots_before_orphaned_ones(qtbot):
    overlay, _parent = _overlay(qtbot)
    document = _document()
    document.theme.slots[0].orphaned = True  # White, first in theme order
    document.add_card(Card(id="c_1", color_slot="slot_white"))
    document.add_card(Card(id="c_2", color_slot="slot_blue"))
    document.set_color_key_visible(True)
    overlay.set_document(document)

    labels = [slot.label for slot in overlay._entries()]

    assert labels == ["Blue", "White"]


def test_switching_documents_disconnects_the_previous_one(qtbot):
    overlay, _parent = _overlay(qtbot)
    first = _document()
    first.add_card(Card(id="c_1"))
    first.set_color_key_visible(True)
    overlay.set_document(first)

    second = _document()
    overlay.set_document(second)

    # Mutating the no-longer-watched first document must not raise (would,
    # if a stale connection tried to call back into a torn-down overlay
    # state) and must not affect the overlay's now-empty entries.
    first.add_card(Card(id="c_2"))
    assert overlay._entries() == []


def test_resize_repositions_to_bottom_right(qtbot):
    overlay, parent = _overlay(qtbot)
    document = _document()
    document.add_card(Card(id="c_1"))
    document.set_color_key_visible(True)
    overlay.set_document(document)

    overlay.reposition(parent.size())

    assert overlay.geometry().right() <= parent.width()
    assert overlay.geometry().bottom() <= parent.height()
