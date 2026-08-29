from __future__ import annotations

from PySide6.QtCore import QSettings

_KEY_WARN_BEFORE_DELETE = "warnBeforeDelete"
_KEY_DEFAULT_THEME_ID = "defaultThemeId"
_LEGACY_KEY_DEFAULT_BACKGROUND_COLOR = "defaultBackgroundColor"
_KEY_LIMIT_ARRANGE_COLUMNS = "limitArrangeColumns"
_KEY_ARRANGE_COLUMN_LIMIT = "arrangeColumnLimit"

DEFAULT_ARRANGE_COLUMN_LIMIT = 12
MIN_ARRANGE_COLUMN_LIMIT = 2
DEFAULT_DEFAULT_THEME_ID = "preset_classic"


class AppSettings:
    """Application-wide user preferences, shared across all windows via
    WindowManager.settings.

    backing=None (the default — and what every fallback/test construction
    path uses) keeps values purely in memory so tests never touch the
    developer's real preferences file; only app.py's production entry
    point supplies a real QSettings backing.
    """

    def __init__(self, backing: QSettings | None = None) -> None:
        self._backing = backing
        if backing is not None:
            self._warn_before_delete = bool(
                backing.value(_KEY_WARN_BEFORE_DELETE, True, type=bool)
            )
            had_theme_id = backing.contains(_KEY_DEFAULT_THEME_ID)
            self._default_theme_id = str(
                backing.value(_KEY_DEFAULT_THEME_ID, DEFAULT_DEFAULT_THEME_ID, type=str)
            )
            self._legacy_background_color: str | None = None
            if not had_theme_id and backing.contains(_LEGACY_KEY_DEFAULT_BACKGROUND_COLOR):
                self._legacy_background_color = str(
                    backing.value(_LEGACY_KEY_DEFAULT_BACKGROUND_COLOR, "", type=str)
                )
            self._limit_arrange_columns = bool(
                backing.value(_KEY_LIMIT_ARRANGE_COLUMNS, False, type=bool)
            )
            self._arrange_column_limit = max(
                MIN_ARRANGE_COLUMN_LIMIT,
                int(
                    backing.value(
                        _KEY_ARRANGE_COLUMN_LIMIT, DEFAULT_ARRANGE_COLUMN_LIMIT, type=int
                    )
                ),
            )
        else:
            self._warn_before_delete = True
            self._default_theme_id = DEFAULT_DEFAULT_THEME_ID
            self._legacy_background_color = None
            self._limit_arrange_columns = False
            self._arrange_column_limit = DEFAULT_ARRANGE_COLUMN_LIMIT

    @property
    def warn_before_delete(self) -> bool:
        return self._warn_before_delete

    @warn_before_delete.setter
    def warn_before_delete(self, value: bool) -> None:
        self._warn_before_delete = value
        if self._backing is not None:
            self._backing.setValue(_KEY_WARN_BEFORE_DELETE, value)

    @property
    def default_theme_id(self) -> str:
        return self._default_theme_id

    @default_theme_id.setter
    def default_theme_id(self, value: str) -> None:
        self._default_theme_id = value
        if self._backing is not None:
            self._backing.setValue(_KEY_DEFAULT_THEME_ID, value)

    @property
    def legacy_background_color(self) -> str | None:
        """The old single default-background-color setting's raw value —
        non-None exactly once, right after upgrading from a version of
        this app that predates the theme system and had no
        default_theme_id at all. theme_resolution.resolve_default_theme()
        consumes this to synthesize a one-time 'Legacy Default' custom
        theme (rather than silently discarding the user's prior
        customization) and persists a real default_theme_id, so this
        never fires again on a later launch."""
        return self._legacy_background_color

    @property
    def limit_arrange_columns(self) -> bool:
        return self._limit_arrange_columns

    @limit_arrange_columns.setter
    def limit_arrange_columns(self, value: bool) -> None:
        self._limit_arrange_columns = value
        if self._backing is not None:
            self._backing.setValue(_KEY_LIMIT_ARRANGE_COLUMNS, value)

    @property
    def arrange_column_limit(self) -> int:
        return self._arrange_column_limit

    @arrange_column_limit.setter
    def arrange_column_limit(self, value: int) -> None:
        self._arrange_column_limit = max(MIN_ARRANGE_COLUMN_LIMIT, value)
        if self._backing is not None:
            self._backing.setValue(_KEY_ARRANGE_COLUMN_LIMIT, self._arrange_column_limit)
