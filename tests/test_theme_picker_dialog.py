from indexcards.models.theme import Theme
from indexcards.theme_library import ThemeLibrary
from indexcards.widgets.theme_picker_dialog import ThemePickerDialog

_PRESET = Theme(
    id="preset_classic",
    name="Classic",
    origin="preset",
    background_color="#3d6b4f",
    slots=[],
)
_CUSTOM = Theme(id="custom_1", name="Mine", origin="custom", background_color="#123456", slots=[])


def test_lists_every_available_theme(qtbot):
    dialog = ThemePickerDialog([_PRESET, _CUSTOM], "preset_classic", ThemeLibrary())
    qtbot.addWidget(dialog)

    assert dialog.theme_list.count() == 2


def test_current_theme_is_preselected(qtbot):
    dialog = ThemePickerDialog([_PRESET, _CUSTOM], "custom_1", ThemeLibrary())
    qtbot.addWidget(dialog)

    assert dialog.chosen_theme().id == "custom_1"


def test_selecting_a_different_row_changes_chosen_theme(qtbot):
    dialog = ThemePickerDialog([_PRESET, _CUSTOM], "preset_classic", ThemeLibrary())
    qtbot.addWidget(dialog)

    dialog.theme_list.setCurrentRow(1)

    assert dialog.chosen_theme().id == "custom_1"


def test_chosen_theme_is_none_with_no_selection(qtbot):
    dialog = ThemePickerDialog([_PRESET, _CUSTOM], "preset_classic", ThemeLibrary())
    qtbot.addWidget(dialog)
    dialog.theme_list.setCurrentRow(-1)

    assert dialog.chosen_theme() is None


def test_duplicate_adds_a_new_row_and_selects_it(qtbot, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *a, **k: ("My Copy", True))
    )
    library = ThemeLibrary()
    dialog = ThemePickerDialog([_PRESET], "preset_classic", library)
    qtbot.addWidget(dialog)

    dialog._on_duplicate()

    assert dialog.theme_list.count() == 2
    chosen = dialog.chosen_theme()
    assert chosen.name == "My Copy"
    assert chosen.origin == "custom"


def test_duplicate_persists_to_the_theme_library(qtbot, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *a, **k: ("My Copy", True))
    )
    library = ThemeLibrary()
    dialog = ThemePickerDialog([_PRESET], "preset_classic", library)
    qtbot.addWidget(dialog)

    dialog._on_duplicate()

    assert len(library.all()) == 1
    assert library.all()[0].name == "My Copy"


def test_duplicate_preserves_source_slot_ids(qtbot, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *a, **k: ("My Copy", True))
    )
    from indexcards.models.theme import Slot

    source = Theme(
        id="preset_classic",
        name="Classic",
        origin="preset",
        background_color="#3d6b4f",
        slots=[Slot(id="slot_white", label="White", hex="#ffffff")],
    )
    library = ThemeLibrary()
    dialog = ThemePickerDialog([source], "preset_classic", library)
    qtbot.addWidget(dialog)

    dialog._on_duplicate()

    duplicated = dialog.chosen_theme()
    assert [slot.id for slot in duplicated.slots] == ["slot_white"]


def test_cancelling_duplicate_prompt_adds_nothing(qtbot, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("", False)))
    library = ThemeLibrary()
    dialog = ThemePickerDialog([_PRESET], "preset_classic", library)
    qtbot.addWidget(dialog)

    dialog._on_duplicate()

    assert dialog.theme_list.count() == 1
    assert library.all() == []


def test_duplicate_with_no_selection_is_a_noop(qtbot):
    library = ThemeLibrary()
    dialog = ThemePickerDialog([_PRESET], "preset_classic", library)
    qtbot.addWidget(dialog)
    dialog.theme_list.setCurrentRow(-1)

    dialog._on_duplicate()

    assert dialog.theme_list.count() == 1
    assert library.all() == []
