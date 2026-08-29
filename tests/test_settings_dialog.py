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
    )
    qtbot.addWidget(dialog)

    dialog.warn_before_delete_checkbox.setChecked(False)

    assert dialog.warn_before_delete() is False


def test_theme_combo_lists_every_available_theme(qtbot):
    dialog = SettingsDialog(
        warn_before_delete=True,
        default_theme_id="preset_classic",
        available_themes=_AVAILABLE_THEMES,
        limit_arrange_columns=False,
        arrange_column_limit=12,
    )
    qtbot.addWidget(dialog)

    assert dialog.default_theme_combo.count() == len(_AVAILABLE_THEMES)


def test_theme_combo_labels_presets_distinctly_from_custom_themes(qtbot):
    dialog = SettingsDialog(
        warn_before_delete=True,
        default_theme_id="preset_classic",
        available_themes=_AVAILABLE_THEMES,
        limit_arrange_columns=False,
        arrange_column_limit=12,
    )
    qtbot.addWidget(dialog)

    combo = dialog.default_theme_combo
    labels = [combo.itemText(i) for i in range(combo.count())]
    assert "Classic (preset)" in labels
    assert "My Theme" in labels


def test_selecting_a_different_theme_updates_default_theme_id(qtbot):
    dialog = SettingsDialog(
        warn_before_delete=True,
        default_theme_id="preset_classic",
        available_themes=_AVAILABLE_THEMES,
        limit_arrange_columns=False,
        arrange_column_limit=12,
    )
    qtbot.addWidget(dialog)

    position = dialog.default_theme_combo.findData("custom_1")
    dialog.default_theme_combo.setCurrentIndex(position)

    assert dialog.default_theme_id() == "custom_1"


def test_falls_back_to_first_theme_when_default_theme_id_not_found(qtbot):
    dialog = SettingsDialog(
        warn_before_delete=True,
        default_theme_id="does_not_exist",
        available_themes=_AVAILABLE_THEMES,
        limit_arrange_columns=False,
        arrange_column_limit=12,
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
    )
    qtbot.addWidget(dialog)

    dialog.accept()

    assert dialog.result() == QDialog.DialogCode.Accepted
