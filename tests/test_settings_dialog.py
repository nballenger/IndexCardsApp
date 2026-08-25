from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog, QDialog

from indexcards.widgets.settings_dialog import SettingsDialog


def test_constructor_seeds_widgets_from_passed_in_values(qtbot):
    dialog = SettingsDialog(
        warn_before_delete=True,
        default_background_color="#3d6b4f",
        limit_arrange_columns=False,
        arrange_column_limit=12,
    )
    qtbot.addWidget(dialog)

    assert dialog.warn_before_delete_checkbox.isChecked() is True
    assert dialog.default_background_color() == "#3d6b4f"


def test_constructor_seeds_unchecked_warning(qtbot):
    dialog = SettingsDialog(
        warn_before_delete=False,
        default_background_color="#3d6b4f",
        limit_arrange_columns=False,
        arrange_column_limit=12,
    )
    qtbot.addWidget(dialog)

    assert dialog.warn_before_delete_checkbox.isChecked() is False


def test_warn_before_delete_accessor_reflects_toggled_state(qtbot):
    dialog = SettingsDialog(
        warn_before_delete=True,
        default_background_color="#3d6b4f",
        limit_arrange_columns=False,
        arrange_column_limit=12,
    )
    qtbot.addWidget(dialog)

    dialog.warn_before_delete_checkbox.setChecked(False)

    assert dialog.warn_before_delete() is False


def test_picking_a_color_updates_default_background_color(qtbot, monkeypatch):
    monkeypatch.setattr(QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor("#abcdef")))
    dialog = SettingsDialog(
        warn_before_delete=True,
        default_background_color="#3d6b4f",
        limit_arrange_columns=False,
        arrange_column_limit=12,
    )
    qtbot.addWidget(dialog)

    dialog.background_color_button.click()

    assert dialog.default_background_color() == "#abcdef"


def test_cancelling_color_picker_leaves_color_unchanged(qtbot, monkeypatch):
    monkeypatch.setattr(QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor()))
    dialog = SettingsDialog(
        warn_before_delete=True,
        default_background_color="#3d6b4f",
        limit_arrange_columns=False,
        arrange_column_limit=12,
    )
    qtbot.addWidget(dialog)

    dialog.background_color_button.click()

    assert dialog.default_background_color() == "#3d6b4f"


def test_constructor_seeds_column_limit_widgets(qtbot):
    dialog = SettingsDialog(
        warn_before_delete=True,
        default_background_color="#3d6b4f",
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
        default_background_color="#3d6b4f",
        limit_arrange_columns=False,
        arrange_column_limit=12,
    )
    qtbot.addWidget(dialog)

    assert dialog.arrange_column_limit_edit.isEnabled() is False


def test_checking_limit_checkbox_enables_column_limit_edit(qtbot):
    dialog = SettingsDialog(
        warn_before_delete=True,
        default_background_color="#3d6b4f",
        limit_arrange_columns=False,
        arrange_column_limit=12,
    )
    qtbot.addWidget(dialog)

    dialog.limit_arrange_columns_checkbox.setChecked(True)

    assert dialog.arrange_column_limit_edit.isEnabled() is True


def test_accessors_reflect_column_limit_state(qtbot):
    dialog = SettingsDialog(
        warn_before_delete=True,
        default_background_color="#3d6b4f",
        limit_arrange_columns=True,
        arrange_column_limit=7,
    )
    qtbot.addWidget(dialog)

    assert dialog.limit_arrange_columns() is True
    assert dialog.arrange_column_limit() == 7


def test_accept_resets_empty_column_limit_to_default(qtbot):
    dialog = SettingsDialog(
        warn_before_delete=True,
        default_background_color="#3d6b4f",
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
        default_background_color="#3d6b4f",
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
        default_background_color="#3d6b4f",
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
        default_background_color="#3d6b4f",
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
        default_background_color="#3d6b4f",
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
        default_background_color="#3d6b4f",
        limit_arrange_columns=False,
        arrange_column_limit=12,
    )
    qtbot.addWidget(dialog)

    dialog.accept()

    assert dialog.result() == QDialog.DialogCode.Accepted
