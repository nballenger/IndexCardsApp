from indexcards.models.document import Document
from indexcards.models.theme import Slot, Theme
from indexcards.widgets.orphan_resolution_dialog import OrphanResolutionDialog


def _document_with_orphans() -> Document:
    theme = Theme(
        id="t_1",
        name="Test",
        origin="custom",
        background_color="#3d6b4f",
        slots=[
            Slot(id="slot_active", label="Active", hex="#ff0000"),
            Slot(id="slot_orphan_a", label="Orphan A", hex="#00ff00", orphaned=True),
            Slot(id="slot_orphan_b", label="Orphan B", hex="#0000ff", orphaned=True),
        ],
    )
    return Document(name="Test", theme=theme)


def test_one_row_per_orphan_slot(qtbot):
    document = _document_with_orphans()
    dialog = OrphanResolutionDialog(document, ["slot_orphan_a", "slot_orphan_b"])
    qtbot.addWidget(dialog)

    assert len(dialog._rows) == 2


def test_rows_default_to_keep(qtbot):
    document = _document_with_orphans()
    dialog = OrphanResolutionDialog(document, ["slot_orphan_a"])
    qtbot.addWidget(dialog)

    assert dialog.resolutions() == [("slot_orphan_a", None)]


def test_ok_enabled_by_default_with_all_rows_kept(qtbot):
    document = _document_with_orphans()
    dialog = OrphanResolutionDialog(document, ["slot_orphan_a", "slot_orphan_b"])
    qtbot.addWidget(dialog)

    ok_button = dialog.button_box.button(dialog.button_box.StandardButton.Ok)
    assert ok_button.isEnabled() is True


def test_selecting_reassign_without_a_target_disables_ok(qtbot):
    document = _document_with_orphans()
    dialog = OrphanResolutionDialog(document, ["slot_orphan_a"])
    qtbot.addWidget(dialog)

    dialog._rows[0].reassign_radio.setChecked(True)
    dialog._rows[0].target_combo.setCurrentIndex(-1)

    ok_button = dialog.button_box.button(dialog.button_box.StandardButton.Ok)
    assert ok_button.isEnabled() is False


def test_selecting_reassign_with_a_target_enables_ok_and_reflects_in_resolutions(qtbot):
    document = _document_with_orphans()
    dialog = OrphanResolutionDialog(document, ["slot_orphan_a"])
    qtbot.addWidget(dialog)

    dialog._rows[0].reassign_radio.setChecked(True)
    position = dialog._rows[0].target_combo.findData("slot_active")
    dialog._rows[0].target_combo.setCurrentIndex(position)

    ok_button = dialog.button_box.button(dialog.button_box.StandardButton.Ok)
    assert ok_button.isEnabled() is True
    assert dialog.resolutions() == [("slot_orphan_a", "slot_active")]


def test_target_combo_excludes_orphaned_slots(qtbot):
    document = _document_with_orphans()
    dialog = OrphanResolutionDialog(document, ["slot_orphan_a"])
    qtbot.addWidget(dialog)

    combo = dialog._rows[0].target_combo
    target_ids = {combo.itemData(i) for i in range(combo.count())}
    assert target_ids == {"slot_active"}


def test_target_combo_excludes_the_row_own_orphan_slot(qtbot):
    document = _document_with_orphans()
    dialog = OrphanResolutionDialog(document, ["slot_orphan_a", "slot_orphan_b"])
    qtbot.addWidget(dialog)

    combo = dialog._rows[0].target_combo
    target_ids = {combo.itemData(i) for i in range(combo.count())}
    assert "slot_orphan_a" not in target_ids


def test_rows_resolved_independently(qtbot):
    document = _document_with_orphans()
    dialog = OrphanResolutionDialog(document, ["slot_orphan_a", "slot_orphan_b"])
    qtbot.addWidget(dialog)

    dialog._rows[1].reassign_radio.setChecked(True)
    position = dialog._rows[1].target_combo.findData("slot_active")
    dialog._rows[1].target_combo.setCurrentIndex(position)

    assert dialog.resolutions() == [
        ("slot_orphan_a", None),
        ("slot_orphan_b", "slot_active"),
    ]


def test_switching_back_to_keep_reenables_ok(qtbot):
    document = _document_with_orphans()
    dialog = OrphanResolutionDialog(document, ["slot_orphan_a"])
    qtbot.addWidget(dialog)
    dialog._rows[0].reassign_radio.setChecked(True)
    dialog._rows[0].target_combo.setCurrentIndex(-1)
    assert dialog.button_box.button(dialog.button_box.StandardButton.Ok).isEnabled() is False

    dialog._rows[0].keep_radio.setChecked(True)

    assert dialog.button_box.button(dialog.button_box.StandardButton.Ok).isEnabled() is True
