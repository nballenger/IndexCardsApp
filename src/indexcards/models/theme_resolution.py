from __future__ import annotations

from indexcards.app_settings import AppSettings
from indexcards.models.presets import PRESET_THEMES, get_preset_theme
from indexcards.models.theme import Theme, clone_theme, duplicate_theme
from indexcards.theme_library import ThemeLibrary

LEGACY_DEFAULT_THEME_ID = "legacy_default"


def resolve_default_theme(settings: AppSettings, library: ThemeLibrary) -> Theme:
    """The theme a brand-new document should start from: an independent
    clone (see clone_theme), ready to hand straight to Document(theme=...).

    Falls back to the placeholder preset if settings.default_theme_id
    points at a theme that no longer exists (e.g. a deleted custom
    theme). See AppSettings.legacy_background_color's docstring for the
    one-time upgrade path this also handles.
    """
    if settings.legacy_background_color is not None:
        if library.get(LEGACY_DEFAULT_THEME_ID) is None:
            legacy_theme = duplicate_theme(
                PRESET_THEMES[0], LEGACY_DEFAULT_THEME_ID, "Legacy Default"
            )
            legacy_theme.background_color = settings.legacy_background_color
            library.add(legacy_theme)
        settings.default_theme_id = LEGACY_DEFAULT_THEME_ID

    theme_id = settings.default_theme_id
    theme = get_preset_theme(theme_id) or library.get(theme_id) or PRESET_THEMES[0]
    return clone_theme(theme)
