from __future__ import annotations

from PySide6.QtCore import QSettings

from indexcards.models.document import DEFAULT_CANVAS_BACKGROUND_COLOR

_KEY_WARN_BEFORE_DELETE = "warnBeforeDelete"
_KEY_DEFAULT_BACKGROUND_COLOR = "defaultBackgroundColor"


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
        else:
            self._warn_before_delete = True
            self._default_background_color = DEFAULT_CANVAS_BACKGROUND_COLOR

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
