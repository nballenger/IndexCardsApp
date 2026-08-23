from indexcards.widgets.arrange_dialog import ArrangeDialog


def test_defaults_to_color_mode(qtbot):
    dialog = ArrangeDialog(["plot", "urgent"])
    qtbot.addWidget(dialog)

    assert dialog.selected_group_by() == "color"
    assert dialog.selected_tag() is None


def test_selecting_tag_radio_still_reports_color_when_tags_disabled(qtbot):
    dialog = ArrangeDialog(["plot", "urgent"])
    qtbot.addWidget(dialog)

    dialog.tag_radio.setChecked(True)
    dialog.tag_combo.setCurrentText("urgent")

    assert dialog.selected_group_by() == "color"
    assert dialog.selected_tag() is None


def test_tag_controls_hidden_when_tags_disabled(qtbot):
    dialog = ArrangeDialog(["plot", "urgent"])
    qtbot.addWidget(dialog)

    # Regression: parented but left out of any layout still made these
    # visible at their default (0, 0) position, overlapping color_radio,
    # unless explicitly hidden. isHidden() (not isVisible(), which would
    # be False either way since the dialog itself is never shown here)
    # reflects whether setVisible(False) was actually called on them.
    assert dialog.tag_radio.isHidden() is True
    assert dialog.tag_combo.isHidden() is True


def test_tag_controls_not_hidden_when_tags_enabled(qtbot, monkeypatch):
    monkeypatch.setattr("indexcards.widgets.arrange_dialog.TAGS_ENABLED", True)
    dialog = ArrangeDialog(["plot", "urgent"])
    qtbot.addWidget(dialog)

    assert dialog.tag_radio.isHidden() is False
    assert dialog.tag_combo.isHidden() is False


def test_selecting_tag_mode_reports_chosen_tag_when_tags_enabled(qtbot, monkeypatch):
    monkeypatch.setattr("indexcards.widgets.arrange_dialog.TAGS_ENABLED", True)
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


def test_selecting_tile_radio_reports_tile():
    dialog = ArrangeDialog(["plot", "urgent"])

    dialog.tile_radio.setChecked(True)

    assert dialog.selected_group_by() == "tile"
    assert dialog.selected_tag() is None


def test_tile_radio_available_regardless_of_tags_flag(qtbot, monkeypatch):
    monkeypatch.setattr("indexcards.widgets.arrange_dialog.TAGS_ENABLED", False)
    dialog = ArrangeDialog([])
    qtbot.addWidget(dialog)

    assert dialog.tile_radio.isEnabled() is True
    assert dialog.tile_radio.isHidden() is False


def test_selecting_tile_radio_unchecks_color_radio(qtbot):
    dialog = ArrangeDialog(["plot"])
    qtbot.addWidget(dialog)
    assert dialog.color_radio.isChecked() is True

    dialog.tile_radio.setChecked(True)

    assert dialog.color_radio.isChecked() is False


def test_selecting_scatter_radio_reports_scatter():
    dialog = ArrangeDialog(["plot", "urgent"])

    dialog.scatter_radio.setChecked(True)

    assert dialog.selected_group_by() == "scatter"
    assert dialog.selected_tag() is None


def test_scatter_radio_available_regardless_of_tags_flag(qtbot, monkeypatch):
    monkeypatch.setattr("indexcards.widgets.arrange_dialog.TAGS_ENABLED", False)
    dialog = ArrangeDialog([])
    qtbot.addWidget(dialog)

    assert dialog.scatter_radio.isEnabled() is True
    assert dialog.scatter_radio.isHidden() is False


def test_selecting_scatter_radio_unchecks_color_radio(qtbot):
    dialog = ArrangeDialog(["plot"])
    qtbot.addWidget(dialog)
    assert dialog.color_radio.isChecked() is True

    dialog.scatter_radio.setChecked(True)

    assert dialog.color_radio.isChecked() is False
