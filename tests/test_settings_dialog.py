from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog

from indexcards.widgets.settings_dialog import SettingsDialog


def test_constructor_seeds_widgets_from_passed_in_values(qtbot):
    dialog = SettingsDialog(warn_before_delete=True, default_background_color="#3d6b4f")
    qtbot.addWidget(dialog)

    assert dialog.warn_before_delete_checkbox.isChecked() is True
    assert dialog.default_background_color() == "#3d6b4f"


def test_constructor_seeds_unchecked_warning(qtbot):
    dialog = SettingsDialog(warn_before_delete=False, default_background_color="#3d6b4f")
    qtbot.addWidget(dialog)

    assert dialog.warn_before_delete_checkbox.isChecked() is False


def test_warn_before_delete_accessor_reflects_toggled_state(qtbot):
    dialog = SettingsDialog(warn_before_delete=True, default_background_color="#3d6b4f")
    qtbot.addWidget(dialog)

    dialog.warn_before_delete_checkbox.setChecked(False)

    assert dialog.warn_before_delete() is False


def test_picking_a_color_updates_default_background_color(qtbot, monkeypatch):
    monkeypatch.setattr(QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor("#abcdef")))
    dialog = SettingsDialog(warn_before_delete=True, default_background_color="#3d6b4f")
    qtbot.addWidget(dialog)

    dialog.background_color_button.click()

    assert dialog.default_background_color() == "#abcdef"


def test_cancelling_color_picker_leaves_color_unchanged(qtbot, monkeypatch):
    monkeypatch.setattr(QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor()))
    dialog = SettingsDialog(warn_before_delete=True, default_background_color="#3d6b4f")
    qtbot.addWidget(dialog)

    dialog.background_color_button.click()

    assert dialog.default_background_color() == "#3d6b4f"
