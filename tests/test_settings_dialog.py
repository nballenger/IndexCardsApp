from PySide6.QtWidgets import QDialog

from indexcards.models.presets import PRESET_THEMES
from indexcards.models.theme import Theme
from indexcards.widgets.settings_dialog import SettingsDialog

_CUSTOM_THEME = Theme(id="custom_1", name="My Theme", origin="custom", background_color="#123456")
_AVAILABLE_THEMES = [*PRESET_THEMES, _CUSTOM_THEME]


def test_constructor_seeds_widgets_from_passed_in_values(qtbot):
    dialog = SettingsDialog(
        warn_before_delete=True,
        default_theme_id="preset_classic",
        available_themes=_AVAILABLE_THEMES,
        limit_arrange_columns=False,
        arrange_column_limit=12,
        gather_stacks_edge="left",
        view_on_open="zoom_extents",
    )
    qtbot.addWidget(dialog)

    assert dialog.warn_before_delete_checkbox.isChecked() is True
    assert dialog.default_theme_id() == "preset_classic"


def test_constructor_seeds_unchecked_warning(qtbot):
    dialog = SettingsDialog(
        warn_before_delete=False,
        default_theme_id="preset_classic",
        available_themes=_AVAILABLE_THEMES,
        limit_arrange_columns=False,
        arrange_column_limit=12,
        gather_stacks_edge="left",
        view_on_open="zoom_extents",
    )
    qtbot.addWidget(dialog)

    assert dialog.warn_before_delete_checkbox.isChecked() is False


def test_warn_before_delete_accessor_reflects_toggled_state(qtbot):
    dialog = SettingsDialog(
        warn_before_delete=True,
        default_theme_id="preset_classic",
        available_themes=_AVAILABLE_THEMES,
        limit_arrange_columns=False,
        arrange_column_limit=12,
        gather_stacks_edge="left",
        view_on_open="zoom_extents",
    )
    qtbot.addWidget(dialog)

    dialog.warn_before_delete_checkbox.setChecked(False)

    assert dialog.warn_before_delete() is False


def test_themes_pane_lists_every_available_theme(qtbot):
    dialog = SettingsDialog(
        warn_before_delete=True,
        default_theme_id="preset_classic",
        available_themes=_AVAILABLE_THEMES,
        limit_arrange_columns=False,
        arrange_column_limit=12,
        gather_stacks_edge="left",
        view_on_open="zoom_extents",
    )
    qtbot.addWidget(dialog)

    assert dialog.themes_pane.theme_list.count() == len(_AVAILABLE_THEMES)


def test_themes_pane_lists_theme_names(qtbot):
    dialog = SettingsDialog(
        warn_before_delete=True,
        default_theme_id="preset_classic",
        available_themes=_AVAILABLE_THEMES,
        limit_arrange_columns=False,
        arrange_column_limit=12,
        gather_stacks_edge="left",
        view_on_open="zoom_extents",
    )
    qtbot.addWidget(dialog)

    theme_list = dialog.themes_pane.theme_list
    names = [
        theme_list.itemWidget(theme_list.item(i)).name_edit.text()
        for i in range(theme_list.count())
    ]
    assert "Classic" in names
    assert "My Theme" in names


def test_clicking_default_button_updates_default_theme_id(qtbot):
    dialog = SettingsDialog(
        warn_before_delete=True,
        default_theme_id="preset_classic",
        available_themes=_AVAILABLE_THEMES,
        limit_arrange_columns=False,
        arrange_column_limit=12,
        gather_stacks_edge="left",
        view_on_open="zoom_extents",
    )
    qtbot.addWidget(dialog)
    pane = dialog.themes_pane
    pane._select_row("custom_1")

    pane.default_button.click()

    assert dialog.default_theme_id() == "custom_1"


def test_falls_back_to_first_theme_when_default_theme_id_not_found(qtbot):
    dialog = SettingsDialog(
        warn_before_delete=True,
        default_theme_id="does_not_exist",
        available_themes=_AVAILABLE_THEMES,
        limit_arrange_columns=False,
        arrange_column_limit=12,
        gather_stacks_edge="left",
        view_on_open="zoom_extents",
    )
    qtbot.addWidget(dialog)

    assert dialog.default_theme_id() == _AVAILABLE_THEMES[0].id


def test_constructor_seeds_column_limit_widgets(qtbot):
    dialog = SettingsDialog(
        warn_before_delete=True,
        default_theme_id="preset_classic",
        available_themes=_AVAILABLE_THEMES,
        limit_arrange_columns=True,
        arrange_column_limit=7,
        gather_stacks_edge="left",
        view_on_open="zoom_extents",
    )
    qtbot.addWidget(dialog)

    assert dialog.limit_arrange_columns_checkbox.isChecked() is True
    assert dialog.arrange_column_limit_edit.text() == "7"
    assert dialog.arrange_column_limit_edit.isEnabled() is True


def test_column_limit_edit_disabled_when_checkbox_unchecked(qtbot):
    dialog = SettingsDialog(
        warn_before_delete=True,
        default_theme_id="preset_classic",
        available_themes=_AVAILABLE_THEMES,
        limit_arrange_columns=False,
        arrange_column_limit=12,
        gather_stacks_edge="left",
        view_on_open="zoom_extents",
    )
    qtbot.addWidget(dialog)

    assert dialog.arrange_column_limit_edit.isEnabled() is False


def test_checking_limit_checkbox_enables_column_limit_edit(qtbot):
    dialog = SettingsDialog(
        warn_before_delete=True,
        default_theme_id="preset_classic",
        available_themes=_AVAILABLE_THEMES,
        limit_arrange_columns=False,
        arrange_column_limit=12,
        gather_stacks_edge="left",
        view_on_open="zoom_extents",
    )
    qtbot.addWidget(dialog)

    dialog.limit_arrange_columns_checkbox.setChecked(True)

    assert dialog.arrange_column_limit_edit.isEnabled() is True


def test_accessors_reflect_column_limit_state(qtbot):
    dialog = SettingsDialog(
        warn_before_delete=True,
        default_theme_id="preset_classic",
        available_themes=_AVAILABLE_THEMES,
        limit_arrange_columns=True,
        arrange_column_limit=7,
        gather_stacks_edge="left",
        view_on_open="zoom_extents",
    )
    qtbot.addWidget(dialog)

    assert dialog.limit_arrange_columns() is True
    assert dialog.arrange_column_limit() == 7


def test_accept_resets_empty_column_limit_to_default(qtbot):
    dialog = SettingsDialog(
        warn_before_delete=True,
        default_theme_id="preset_classic",
        available_themes=_AVAILABLE_THEMES,
        limit_arrange_columns=True,
        arrange_column_limit=7,
        gather_stacks_edge="left",
        view_on_open="zoom_extents",
    )
    qtbot.addWidget(dialog)
    dialog.arrange_column_limit_edit.setText("")

    dialog.accept()

    assert dialog.arrange_column_limit_edit.text() == "12"
    assert dialog.arrange_column_limit() == 12


def test_accept_resets_disallowed_column_limit_to_default(qtbot):
    dialog = SettingsDialog(
        warn_before_delete=True,
        default_theme_id="preset_classic",
        available_themes=_AVAILABLE_THEMES,
        limit_arrange_columns=True,
        arrange_column_limit=7,
        gather_stacks_edge="left",
        view_on_open="zoom_extents",
    )
    qtbot.addWidget(dialog)
    dialog.arrange_column_limit_edit.setText("1")

    dialog.accept()

    assert dialog.arrange_column_limit_edit.text() == "12"
    assert dialog.arrange_column_limit() == 12


def test_accept_resets_non_numeric_column_limit_to_default(qtbot):
    dialog = SettingsDialog(
        warn_before_delete=True,
        default_theme_id="preset_classic",
        available_themes=_AVAILABLE_THEMES,
        limit_arrange_columns=True,
        arrange_column_limit=7,
        gather_stacks_edge="left",
        view_on_open="zoom_extents",
    )
    qtbot.addWidget(dialog)
    dialog.arrange_column_limit_edit.setText("not a number")

    dialog.accept()

    assert dialog.arrange_column_limit_edit.text() == "12"


def test_accept_leaves_valid_column_limit_untouched(qtbot):
    dialog = SettingsDialog(
        warn_before_delete=True,
        default_theme_id="preset_classic",
        available_themes=_AVAILABLE_THEMES,
        limit_arrange_columns=True,
        arrange_column_limit=7,
        gather_stacks_edge="left",
        view_on_open="zoom_extents",
    )
    qtbot.addWidget(dialog)
    dialog.arrange_column_limit_edit.setText("25")

    dialog.accept()

    assert dialog.arrange_column_limit_edit.text() == "25"
    assert dialog.arrange_column_limit() == 25


def test_accept_does_not_touch_column_limit_when_checkbox_unchecked(qtbot):
    dialog = SettingsDialog(
        warn_before_delete=True,
        default_theme_id="preset_classic",
        available_themes=_AVAILABLE_THEMES,
        limit_arrange_columns=False,
        arrange_column_limit=7,
        gather_stacks_edge="left",
        view_on_open="zoom_extents",
    )
    qtbot.addWidget(dialog)
    dialog.arrange_column_limit_edit.setText("not a number")

    dialog.accept()

    assert dialog.arrange_column_limit_edit.text() == "not a number"


def test_accept_sets_dialog_result_accepted(qtbot):
    dialog = SettingsDialog(
        warn_before_delete=True,
        default_theme_id="preset_classic",
        available_themes=_AVAILABLE_THEMES,
        limit_arrange_columns=False,
        arrange_column_limit=12,
        gather_stacks_edge="left",
        view_on_open="zoom_extents",
    )
    qtbot.addWidget(dialog)

    dialog.accept()

    assert dialog.result() == QDialog.DialogCode.Accepted


def test_gather_stacks_edge_combo_lists_options_in_order(qtbot):
    dialog = SettingsDialog(
        warn_before_delete=True,
        default_theme_id="preset_classic",
        available_themes=_AVAILABLE_THEMES,
        limit_arrange_columns=False,
        arrange_column_limit=12,
        gather_stacks_edge="left",
        view_on_open="zoom_extents",
    )
    qtbot.addWidget(dialog)

    combo = dialog.gather_stacks_edge_combo
    labels = [combo.itemText(i) for i in range(combo.count())]
    assert labels == ["Left", "Top", "Right", "Bottom"]


def test_gather_stacks_edge_combo_seeded_from_passed_in_value(qtbot):
    dialog = SettingsDialog(
        warn_before_delete=True,
        default_theme_id="preset_classic",
        available_themes=_AVAILABLE_THEMES,
        limit_arrange_columns=False,
        arrange_column_limit=12,
        gather_stacks_edge="bottom",
        view_on_open="zoom_extents",
    )
    qtbot.addWidget(dialog)

    assert dialog.gather_stacks_edge() == "bottom"


def test_selecting_a_different_gather_stacks_edge_updates_accessor(qtbot):
    dialog = SettingsDialog(
        warn_before_delete=True,
        default_theme_id="preset_classic",
        available_themes=_AVAILABLE_THEMES,
        limit_arrange_columns=False,
        arrange_column_limit=12,
        gather_stacks_edge="left",
        view_on_open="zoom_extents",
    )
    qtbot.addWidget(dialog)

    position = dialog.gather_stacks_edge_combo.findData("right")
    dialog.gather_stacks_edge_combo.setCurrentIndex(position)

    assert dialog.gather_stacks_edge() == "right"


def test_view_on_open_radios_seeded_from_passed_in_value(qtbot):
    dialog = SettingsDialog(
        warn_before_delete=True,
        default_theme_id="preset_classic",
        available_themes=_AVAILABLE_THEMES,
        limit_arrange_columns=False,
        arrange_column_limit=12,
        gather_stacks_edge="left",
        view_on_open="last_save",
    )
    qtbot.addWidget(dialog)

    assert dialog._view_on_open_radios["last_save"].isChecked() is True
    assert dialog._view_on_open_radios["zoom_extents"].isChecked() is False
    assert dialog.view_on_open() == "last_save"


def test_view_on_open_radio_labels_match_options_in_order(qtbot):
    dialog = SettingsDialog(
        warn_before_delete=True,
        default_theme_id="preset_classic",
        available_themes=_AVAILABLE_THEMES,
        limit_arrange_columns=False,
        arrange_column_limit=12,
        gather_stacks_edge="left",
        view_on_open="zoom_extents",
    )
    qtbot.addWidget(dialog)

    assert dialog._view_on_open_radios["zoom_extents"].text() == "All objects / Zoom Extents"
    assert dialog._view_on_open_radios["last_save"].text() == "View from last save"


def test_selecting_a_different_view_on_open_radio_updates_accessor(qtbot):
    dialog = SettingsDialog(
        warn_before_delete=True,
        default_theme_id="preset_classic",
        available_themes=_AVAILABLE_THEMES,
        limit_arrange_columns=False,
        arrange_column_limit=12,
        gather_stacks_edge="left",
        view_on_open="zoom_extents",
    )
    qtbot.addWidget(dialog)

    dialog._view_on_open_radios["last_save"].setChecked(True)

    assert dialog.view_on_open() == "last_save"


def _dialog(**overrides) -> SettingsDialog:
    kwargs = dict(
        warn_before_delete=True,
        default_theme_id="preset_classic",
        available_themes=_AVAILABLE_THEMES,
        limit_arrange_columns=False,
        arrange_column_limit=12,
        gather_stacks_edge="left",
        view_on_open="zoom_extents",
    )
    kwargs.update(overrides)
    return SettingsDialog(**kwargs)


def test_toolbar_buttons_switch_panes(qtbot):
    dialog = _dialog()
    qtbot.addWidget(dialog)

    dialog._nav_buttons[SettingsDialog.Pane.THEMES].click()
    assert dialog._stack.currentWidget() is dialog._themes_pane

    dialog._nav_buttons[SettingsDialog.Pane.WARNINGS].click()
    assert dialog._stack.currentWidget() is dialog._warnings_pane

    dialog._nav_buttons[SettingsDialog.Pane.GENERAL].click()
    assert dialog._stack.currentWidget() is dialog._general_pane


def test_initial_pane_opens_on_the_requested_pane(qtbot):
    dialog = _dialog(initial_pane=SettingsDialog.Pane.THEMES)
    qtbot.addWidget(dialog)

    assert dialog._stack.currentWidget() is dialog._themes_pane
    assert dialog._nav_buttons[SettingsDialog.Pane.THEMES].isChecked() is True


def test_default_sub_label_shown_only_under_the_pending_default(qtbot):
    dialog = _dialog()
    qtbot.addWidget(dialog)
    pane = dialog.themes_pane
    classic_row = pane.theme_list.itemWidget(pane._items["preset_classic"])
    custom_row = pane.theme_list.itemWidget(pane._items["custom_1"])
    assert classic_row.default_label.isHidden() is False
    assert custom_row.default_label.isHidden() is True

    pane._select_row("custom_1")
    pane.default_button.click()

    assert classic_row.default_label.isHidden() is True
    assert custom_row.default_label.isHidden() is False


def test_remove_button_disabled_for_preset_theme(qtbot):
    dialog = _dialog()
    qtbot.addWidget(dialog)
    pane = dialog.themes_pane

    pane._select_row("preset_classic")

    assert pane.remove_button.isEnabled() is False


def test_remove_button_enabled_for_custom_theme(qtbot):
    dialog = _dialog()
    qtbot.addWidget(dialog)
    pane = dialog.themes_pane

    pane._select_row("custom_1")

    assert pane.remove_button.isEnabled() is True


def test_add_button_duplicates_the_selected_theme_and_stages_it_as_an_upsert(qtbot):
    dialog = _dialog()
    qtbot.addWidget(dialog)
    pane = dialog.themes_pane
    pane._select_row("custom_1")

    pane.add_button.click()

    assert pane.theme_list.count() == len(_AVAILABLE_THEMES) + 1
    upserts = dialog.pending_theme_library_upserts()
    assert any(theme.name == "My Theme Copy" for theme in upserts)


def test_add_button_creates_row_already_in_rename_mode(qtbot):
    dialog = _dialog()
    qtbot.addWidget(dialog)
    pane = dialog.themes_pane
    pane._select_row("custom_1")

    pane.add_button.click()

    new_row = pane._row_widget_for(pane._current_theme_id)
    assert new_row.name_edit.isReadOnly() is False


def test_renaming_the_currently_selected_theme_survives_committing_editor_state(qtbot):
    # Regression: the editor's own result_theme() used to echo back
    # whatever name was showing when set_theme() last ran, silently
    # reverting a list-row rename the next time the pane captured the
    # editor's state (e.g. via _commit_current_selection()).
    dialog = _dialog()
    qtbot.addWidget(dialog)
    pane = dialog.themes_pane
    pane._select_row("custom_1")

    row = pane._row_widget_for("custom_1")
    row.start_rename()
    row.name_edit.setText("Renamed")
    row.name_edit.editingFinished.emit()

    upserts = dialog.pending_theme_library_upserts()
    assert any(theme.id == "custom_1" and theme.name == "Renamed" for theme in upserts)


def test_remove_button_stages_a_deletion(qtbot):
    dialog = _dialog()
    qtbot.addWidget(dialog)
    pane = dialog.themes_pane
    pane._select_row("custom_1")

    pane.remove_button.click()

    assert "custom_1" in dialog.pending_theme_library_removals()
    assert pane.theme_list.count() == len(_AVAILABLE_THEMES) - 1


def test_creating_then_deleting_a_theme_in_the_same_session_removes_nothing(qtbot):
    dialog = _dialog()
    qtbot.addWidget(dialog)
    pane = dialog.themes_pane
    pane._select_row("custom_1")
    pane.add_button.click()
    new_theme_id = pane._current_theme_id

    pane.remove_button.click()

    assert dialog.pending_theme_library_removals() == []
    assert all(theme.id != new_theme_id for theme in dialog.pending_theme_library_upserts())


def test_deleting_the_pending_default_theme_falls_back_to_classic(qtbot):
    dialog = _dialog()
    qtbot.addWidget(dialog)
    pane = dialog.themes_pane
    pane._select_row("custom_1")
    pane.default_button.click()
    assert dialog.default_theme_id() == "custom_1"

    pane.remove_button.click()

    assert dialog.default_theme_id() == "preset_classic"


def test_editing_a_theme_then_switching_selection_preserves_the_edit(qtbot):
    dialog = _dialog()
    qtbot.addWidget(dialog)
    pane = dialog.themes_pane
    pane._select_row("custom_1")
    pane.editor._background_color = "#abcdef"
    pane.editor._refresh_background_swatch()

    pane._select_row("preset_classic")

    upserts = dialog.pending_theme_library_upserts()
    assert any(
        theme.id == "custom_1" and theme.background_color == "#abcdef" for theme in upserts
    )


def test_preset_theme_is_read_only_when_not_the_document_theme(qtbot):
    document_theme = Theme(
        id="custom_1", name="My Theme", origin="custom", background_color="#123456"
    )
    dialog = _dialog(document_theme=document_theme)
    qtbot.addWidget(dialog)
    pane = dialog.themes_pane

    pane._select_row("preset_classic")

    assert pane.editor.add_slot_button.isEnabled() is False


def test_document_theme_is_editable_even_if_it_is_a_preset(qtbot):
    document_theme = Theme.from_dict(PRESET_THEMES[0].to_dict())
    dialog = _dialog(document_theme=document_theme)
    qtbot.addWidget(dialog)
    pane = dialog.themes_pane

    pane._select_row("preset_classic")

    assert pane.editor.add_slot_button.isEnabled() is True


def test_editing_the_document_theme_is_reflected_in_edited_document_theme(qtbot):
    document_theme = Theme.from_dict(PRESET_THEMES[0].to_dict())
    dialog = _dialog(document_theme=document_theme)
    qtbot.addWidget(dialog)
    pane = dialog.themes_pane
    pane._select_row("preset_classic")
    pane.editor._background_color = "#000000"
    pane.editor._refresh_background_swatch()

    pane._select_row("custom_1")  # force the editor's pending state to be captured

    edited = dialog.edited_document_theme()
    assert edited is not None
    assert edited.background_color == "#000000"


def test_unedited_document_theme_returns_none(qtbot):
    document_theme = Theme(
        id="custom_1", name="My Theme", origin="custom", background_color="#123456"
    )
    dialog = _dialog(document_theme=document_theme)
    qtbot.addWidget(dialog)

    assert dialog.edited_document_theme() is None


def test_document_theme_was_deleted_true_when_its_theme_is_removed(qtbot):
    document_theme = Theme(
        id="custom_1", name="My Theme", origin="custom", background_color="#123456"
    )
    dialog = _dialog(document_theme=document_theme)
    qtbot.addWidget(dialog)
    pane = dialog.themes_pane
    pane._select_row("custom_1")

    pane.remove_button.click()

    assert dialog.document_theme_was_deleted() is True


def test_document_theme_was_deleted_false_when_nothing_is_removed(qtbot):
    document_theme = Theme(
        id="custom_1", name="My Theme", origin="custom", background_color="#123456"
    )
    dialog = _dialog(document_theme=document_theme)
    qtbot.addWidget(dialog)

    assert dialog.document_theme_was_deleted() is False
