from indexcards.app_settings import AppSettings
from indexcards.models.presets import PRESET_THEMES
from indexcards.models.theme import Theme
from indexcards.models.theme_resolution import LEGACY_DEFAULT_THEME_ID, resolve_default_theme
from indexcards.theme_library import ThemeLibrary


def _temp_backing(tmp_path):
    from PySide6.QtCore import QSettings

    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


def test_resolves_to_placeholder_preset_by_default():
    settings = AppSettings()
    library = ThemeLibrary()

    theme = resolve_default_theme(settings, library)

    assert theme.id == PRESET_THEMES[0].id
    assert theme is not PRESET_THEMES[0]  # independent clone, not the shared preset object


def test_resolves_to_a_custom_theme_in_the_library():
    settings = AppSettings()
    settings.default_theme_id = "custom_1"
    library = ThemeLibrary()
    library.add(Theme(id="custom_1", name="Mine", origin="custom", background_color="#123456"))

    theme = resolve_default_theme(settings, library)

    assert theme.id == "custom_1"
    assert theme.name == "Mine"


def test_falls_back_to_placeholder_preset_when_default_theme_id_is_missing():
    settings = AppSettings()
    settings.default_theme_id = "deleted_custom_theme"
    library = ThemeLibrary()

    theme = resolve_default_theme(settings, library)

    assert theme.id == PRESET_THEMES[0].id


def test_clone_is_independent_of_the_library_entry():
    settings = AppSettings()
    settings.default_theme_id = "custom_1"
    library = ThemeLibrary()
    library.add(Theme(id="custom_1", name="Mine", origin="custom", background_color="#123456"))

    theme = resolve_default_theme(settings, library)
    theme.background_color = "#ffffff"

    assert library.get("custom_1").background_color == "#123456"


def test_legacy_background_color_synthesizes_a_theme_and_persists_default_theme_id(tmp_path):
    backing = _temp_backing(tmp_path)
    backing.setValue("defaultBackgroundColor", "#654321")
    settings = AppSettings(backing)
    library = ThemeLibrary()

    theme = resolve_default_theme(settings, library)

    assert theme.background_color == "#654321"
    assert theme.id == LEGACY_DEFAULT_THEME_ID
    assert library.get(LEGACY_DEFAULT_THEME_ID) is not None
    assert settings.default_theme_id == LEGACY_DEFAULT_THEME_ID


def test_legacy_migration_is_idempotent_across_repeated_calls(tmp_path):
    backing = _temp_backing(tmp_path)
    backing.setValue("defaultBackgroundColor", "#654321")
    settings = AppSettings(backing)
    library = ThemeLibrary()

    resolve_default_theme(settings, library)
    resolve_default_theme(settings, library)

    assert len(library.all()) == 1
