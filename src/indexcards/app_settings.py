from __future__ import annotations

from PySide6.QtCore import QSettings

from indexcards.models.document import DEFAULT_CANVAS_BACKGROUND_COLOR

_KEY_WARN_BEFORE_DELETE = "warnBeforeDelete"
_KEY_DEFAULT_BACKGROUND_COLOR = "defaultBackgroundColor"
_KEY_LIMIT_ARRANGE_COLUMNS = "limitArrangeColumns"
_KEY_ARRANGE_COLUMN_LIMIT = "arrangeColumnLimit"

DEFAULT_ARRANGE_COLUMN_LIMIT = 12
MIN_ARRANGE_COLUMN_LIMIT = 2


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
            self._default_background_color = str(
                backing.value(
                    _KEY_DEFAULT_BACKGROUND_COLOR, DEFAULT_CANVAS_BACKGROUND_COLOR, type=str
                )
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
            self._default_background_color = DEFAULT_CANVAS_BACKGROUND_COLOR
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
    def default_background_color(self) -> str:
        return self._default_background_color

    @default_background_color.setter
    def default_background_color(self, value: str) -> None:
        self._default_background_color = value
        if self._backing is not None:
            self._backing.setValue(_KEY_DEFAULT_BACKGROUND_COLOR, value)

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
