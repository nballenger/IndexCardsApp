from indexcards.widgets.arrange_dialog import ArrangeDialog


def test_defaults_to_color_mode(qtbot):
    dialog = ArrangeDialog(["plot", "urgent"])
    qtbot.addWidget(dialog)

    assert dialog.selected_group_by() == "color"
    assert dialog.selected_tag() is None


def test_selecting_tag_mode_reports_chosen_tag(qtbot):
    dialog = ArrangeDialog(["plot", "urgent"])
    qtbot.addWidget(dialog)

    dialog.tag_radio.setChecked(True)
    dialog.tag_combo.setCurrentText("urgent")

    assert dialog.selected_group_by() == "tag"
    assert dialog.selected_tag() == "urgent"


def test_tag_combo_disabled_until_tag_mode_selected(qtbot):
    dialog = ArrangeDialog(["plot"])
    qtbot.addWidget(dialog)

    assert dialog.tag_combo.isEnabled() is False
    dialog.tag_radio.setChecked(True)
    assert dialog.tag_combo.isEnabled() is True


def test_tag_radio_disabled_when_no_tags_exist(qtbot):
    dialog = ArrangeDialog([])
    qtbot.addWidget(dialog)

    assert dialog.tag_radio.isEnabled() is False
