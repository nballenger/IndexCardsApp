from indexcards.models.theme import Slot, Theme
from indexcards.widgets.theme_editor_widget import ThemeEditorWidget


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


def _other_theme() -> Theme:
    return Theme(
        id="t_2",
        name="Other Theme",
        origin="custom",
        background_color="#000000",
        slots=[Slot(id="slot_c", label="C", hex="#0000ff")],
    )


def test_result_theme_preserves_id_name_origin(qtbot):
    widget = ThemeEditorWidget(_theme())
    qtbot.addWidget(widget)

    result = widget.result_theme()

    assert result.id == "t_1"
    assert result.name == "Test Theme"
    assert result.origin == "custom"


def test_result_theme_reflects_unedited_slots(qtbot):
    widget = ThemeEditorWidget(_theme())
    qtbot.addWidget(widget)

    result = widget.result_theme()

    assert [(slot.id, slot.label, slot.hex) for slot in result.slots] == [
        ("slot_a", "A", "#ff0000"),
        ("slot_b", "B", "#00ff00"),
    ]


def test_editing_label_reflected_in_result(qtbot):
    widget = ThemeEditorWidget(_theme())
    qtbot.addWidget(widget)

    widget._row_widget(0).label_edit.setText("Renamed")

    assert widget.result_theme().slots[0].label == "Renamed"


def test_add_slot_appends_a_new_row(qtbot):
    widget = ThemeEditorWidget(_theme())
    qtbot.addWidget(widget)

    widget._on_add_slot()

    result = widget.result_theme()
    assert len(result.slots) == 3
    assert result.slots[2].label == "New Color"


def test_add_slot_gets_a_fresh_id_not_colliding_with_existing(qtbot):
    widget = ThemeEditorWidget(_theme())
    qtbot.addWidget(widget)

    widget._on_add_slot()

    new_slot_id = widget.result_theme().slots[2].id
    assert new_slot_id not in {"slot_a", "slot_b"}


def test_remove_button_drops_the_row(qtbot):
    widget = ThemeEditorWidget(_theme())
    qtbot.addWidget(widget)

    widget._row_widget(0).remove_button.click()

    result = widget.result_theme()
    assert [slot.id for slot in result.slots] == ["slot_b"]


def test_reordering_rows_reflected_in_result(qtbot):
    widget = ThemeEditorWidget(_theme())
    qtbot.addWidget(widget)

    # Simulate the same take-then-reinsert the list's own internal-move
    # drag/drop performs, without driving an actual drag gesture. The
    # widget reference must be captured before takeItem() — Qt drops the
    # item<->widget association as soon as the item leaves the list.
    item = widget.slot_list.item(0)
    row_widget = widget.slot_list.itemWidget(item)
    widget.slot_list.takeItem(0)
    widget.slot_list.insertItem(1, item)
    widget.slot_list.setItemWidget(item, row_widget)

    result = widget.result_theme()
    assert [slot.id for slot in result.slots] == ["slot_b", "slot_a"]


def test_text_color_combo_defaults_to_auto(qtbot):
    widget = ThemeEditorWidget(_theme())
    qtbot.addWidget(widget)

    result = widget.result_theme()
    assert result.slots[0].text_color is None


def test_switching_text_color_combo_to_custom_sets_a_concrete_override(qtbot):
    widget = ThemeEditorWidget(_theme())
    qtbot.addWidget(widget)
    row = widget._row_widget(0)

    row.text_color_combo.setCurrentIndex(1)

    assert widget.result_theme().slots[0].text_color is not None


def test_switching_text_color_combo_back_to_auto_clears_override(qtbot):
    theme = _theme()
    theme.slots[0].text_color = "#ff00ff"
    widget = ThemeEditorWidget(theme)
    qtbot.addWidget(widget)
    row = widget._row_widget(0)
    assert row.text_color_combo.currentIndex() == 1

    row.text_color_combo.setCurrentIndex(0)

    assert widget.result_theme().slots[0].text_color is None


def test_orphaned_slot_preserves_orphaned_flag_through_result(qtbot):
    theme = _theme()
    theme.slots.append(Slot(id="slot_c", label="C", hex="#0000ff", orphaned=True))
    widget = ThemeEditorWidget(theme)
    qtbot.addWidget(widget)

    result = widget.result_theme()

    assert result.get_slot("slot_c").orphaned is True


def test_changing_background_color_reflected_in_result(qtbot):
    widget = ThemeEditorWidget(_theme())
    qtbot.addWidget(widget)

    widget._background_color = "#abcdef"
    widget._refresh_background_swatch()

    assert widget.result_theme().background_color == "#abcdef"


def test_set_theme_rebuilds_rows_from_the_new_theme(qtbot):
    widget = ThemeEditorWidget(_theme())
    qtbot.addWidget(widget)

    widget.set_theme(_other_theme())

    result = widget.result_theme()
    assert result.id == "t_2"
    assert result.name == "Other Theme"
    assert [slot.id for slot in result.slots] == ["slot_c"]


def test_set_theme_name_updates_result_theme(qtbot):
    widget = ThemeEditorWidget(_theme())
    qtbot.addWidget(widget)

    widget.set_theme_name("Renamed")

    assert widget.result_theme().name == "Renamed"


def test_set_theme_discards_unsaved_edits_from_the_previous_theme(qtbot):
    widget = ThemeEditorWidget(_theme())
    qtbot.addWidget(widget)
    widget._row_widget(0).label_edit.setText("Renamed")

    widget.set_theme(_other_theme())
    widget.set_theme(_theme())

    assert widget.result_theme().slots[0].label == "A"


def test_set_read_only_disables_add_slot_and_background_swatch(qtbot):
    widget = ThemeEditorWidget(_theme())
    qtbot.addWidget(widget)

    widget.set_read_only(True)

    assert widget.add_slot_button.isEnabled() is False
    assert widget.background_swatch_button.isEnabled() is False


def test_set_read_only_disables_existing_rows(qtbot):
    widget = ThemeEditorWidget(_theme())
    qtbot.addWidget(widget)

    widget.set_read_only(True)

    row = widget._row_widget(0)
    assert row.swatch_button.isEnabled() is False
    assert row.label_edit.isReadOnly() is True
    assert row.remove_button.isEnabled() is False


def test_set_read_only_false_restores_editing(qtbot):
    widget = ThemeEditorWidget(_theme())
    qtbot.addWidget(widget)
    widget.set_read_only(True)

    widget.set_read_only(False)

    row = widget._row_widget(0)
    assert row.swatch_button.isEnabled() is True
    assert row.label_edit.isReadOnly() is False
    assert widget.add_slot_button.isEnabled() is True


def test_new_rows_added_after_set_read_only_are_also_read_only(qtbot):
    widget = ThemeEditorWidget(_theme())
    qtbot.addWidget(widget)
    widget.set_read_only(True)

    widget.set_theme(_other_theme())

    row = widget._row_widget(0)
    assert row.label_edit.isReadOnly() is True
