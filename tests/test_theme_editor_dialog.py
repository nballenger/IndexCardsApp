from indexcards.models.theme import Slot, Theme
from indexcards.widgets.theme_editor_dialog import ThemeEditorDialog


def _theme() -> Theme:
    return Theme(
        id="t_1",
        name="Test Theme",
        origin="custom",
        background_color="#3d6b4f",
        slots=[
            Slot(id="slot_a", label="A", hex="#ff0000"),
            Slot(id="slot_b", label="B", hex="#00ff00"),
        ],
    )


def test_result_theme_preserves_id_name_origin(qtbot):
    dialog = ThemeEditorDialog(_theme())
    qtbot.addWidget(dialog)

    result = dialog.result_theme()

    assert result.id == "t_1"
    assert result.name == "Test Theme"
    assert result.origin == "custom"


def test_result_theme_reflects_unedited_slots(qtbot):
    dialog = ThemeEditorDialog(_theme())
    qtbot.addWidget(dialog)

    result = dialog.result_theme()

    assert [(slot.id, slot.label, slot.hex) for slot in result.slots] == [
        ("slot_a", "A", "#ff0000"),
        ("slot_b", "B", "#00ff00"),
    ]


def test_editing_label_reflected_in_result(qtbot):
    dialog = ThemeEditorDialog(_theme())
    qtbot.addWidget(dialog)

    dialog._row_widget(0).label_edit.setText("Renamed")

    assert dialog.result_theme().slots[0].label == "Renamed"


def test_add_slot_appends_a_new_row(qtbot):
    dialog = ThemeEditorDialog(_theme())
    qtbot.addWidget(dialog)

    dialog._on_add_slot()

    result = dialog.result_theme()
    assert len(result.slots) == 3
    assert result.slots[2].label == "New Color"


def test_add_slot_gets_a_fresh_id_not_colliding_with_existing(qtbot):
    dialog = ThemeEditorDialog(_theme())
    qtbot.addWidget(dialog)

    dialog._on_add_slot()

    new_slot_id = dialog.result_theme().slots[2].id
    assert new_slot_id not in {"slot_a", "slot_b"}


def test_remove_button_drops_the_row(qtbot):
    dialog = ThemeEditorDialog(_theme())
    qtbot.addWidget(dialog)

    dialog._row_widget(0).remove_button.click()

    result = dialog.result_theme()
    assert [slot.id for slot in result.slots] == ["slot_b"]


def test_reordering_rows_reflected_in_result(qtbot):
    dialog = ThemeEditorDialog(_theme())
    qtbot.addWidget(dialog)

    # Simulate the same take-then-reinsert the list's own internal-move
    # drag/drop performs, without driving an actual drag gesture. The
    # widget reference must be captured before takeItem() — Qt drops the
    # item<->widget association as soon as the item leaves the list.
    item = dialog.slot_list.item(0)
    widget = dialog.slot_list.itemWidget(item)
    dialog.slot_list.takeItem(0)
    dialog.slot_list.insertItem(1, item)
    dialog.slot_list.setItemWidget(item, widget)

    result = dialog.result_theme()
    assert [slot.id for slot in result.slots] == ["slot_b", "slot_a"]


def test_text_color_combo_defaults_to_auto(qtbot):
    dialog = ThemeEditorDialog(_theme())
    qtbot.addWidget(dialog)

    result = dialog.result_theme()
    assert result.slots[0].text_color is None


def test_switching_text_color_combo_to_custom_sets_a_concrete_override(qtbot):
    dialog = ThemeEditorDialog(_theme())
    qtbot.addWidget(dialog)
    row = dialog._row_widget(0)

    row.text_color_combo.setCurrentIndex(1)

    assert dialog.result_theme().slots[0].text_color is not None


def test_switching_text_color_combo_back_to_auto_clears_override(qtbot):
    theme = _theme()
    theme.slots[0].text_color = "#ff00ff"
    dialog = ThemeEditorDialog(theme)
    qtbot.addWidget(dialog)
    row = dialog._row_widget(0)
    assert row.text_color_combo.currentIndex() == 1

    row.text_color_combo.setCurrentIndex(0)

    assert dialog.result_theme().slots[0].text_color is None


def test_orphaned_slot_preserves_orphaned_flag_through_result(qtbot):
    theme = _theme()
    theme.slots.append(Slot(id="slot_c", label="C", hex="#0000ff", orphaned=True))
    dialog = ThemeEditorDialog(theme)
    qtbot.addWidget(dialog)

    result = dialog.result_theme()

    assert result.get_slot("slot_c").orphaned is True


def test_changing_background_color_reflected_in_result(qtbot):
    dialog = ThemeEditorDialog(_theme())
    qtbot.addWidget(dialog)

    dialog._background_color = "#abcdef"
    dialog._refresh_background_swatch()

    assert dialog.result_theme().background_color == "#abcdef"
