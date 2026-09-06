from __future__ import annotations

from PySide6.QtCore import QSettings

_KEY_WARN_BEFORE_DELETE = "warnBeforeDelete"
_KEY_DEFAULT_THEME_ID = "defaultThemeId"
_LEGACY_KEY_DEFAULT_BACKGROUND_COLOR = "defaultBackgroundColor"
_KEY_LIMIT_ARRANGE_COLUMNS = "limitArrangeColumns"
_KEY_ARRANGE_COLUMN_LIMIT = "arrangeColumnLimit"
_KEY_GATHER_STACKS_EDGE = "gatherStacksEdge"
_KEY_VIEW_ON_OPEN = "viewOnOpen"

DEFAULT_ARRANGE_COLUMN_LIMIT = 12
MIN_ARRANGE_COLUMN_LIMIT = 2
DEFAULT_DEFAULT_THEME_ID = "preset_classic"

# (stored value, dropdown label) in the exact order the Settings dialog
# should list them.
GATHER_STACKS_EDGE_OPTIONS: list[tuple[str, str]] = [
    ("left", "Left"),
    ("top", "Top"),
    ("right", "Right"),
    ("bottom", "Bottom"),
]
DEFAULT_GATHER_STACKS_EDGE = "left"

# (stored value, radio button label) in the exact order the Settings
# dialog should list them.
VIEW_ON_OPEN_OPTIONS: list[tuple[str, str]] = [
    ("zoom_extents", "All objects / Zoom Extents"),
    ("last_save", "View from last save"),
]
DEFAULT_VIEW_ON_OPEN = "zoom_extents"


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
            stored_edge = str(
                backing.value(_KEY_GATHER_STACKS_EDGE, DEFAULT_GATHER_STACKS_EDGE, type=str)
            )
            valid_edges = {value for value, _label in GATHER_STACKS_EDGE_OPTIONS}
            self._gather_stacks_edge = (
                stored_edge if stored_edge in valid_edges else DEFAULT_GATHER_STACKS_EDGE
            )
            stored_view_on_open = str(
                backing.value(_KEY_VIEW_ON_OPEN, DEFAULT_VIEW_ON_OPEN, type=str)
            )
            valid_view_on_open = {value for value, _label in VIEW_ON_OPEN_OPTIONS}
            self._view_on_open = (
                stored_view_on_open
                if stored_view_on_open in valid_view_on_open
                else DEFAULT_VIEW_ON_OPEN
            )
        else:
            self._warn_before_delete = True
            self._default_theme_id = DEFAULT_DEFAULT_THEME_ID
            self._legacy_background_color = None
            self._limit_arrange_columns = False
            self._arrange_column_limit = DEFAULT_ARRANGE_COLUMN_LIMIT
            self._gather_stacks_edge = DEFAULT_GATHER_STACKS_EDGE
            self._view_on_open = DEFAULT_VIEW_ON_OPEN

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

    @property
    def gather_stacks_edge(self) -> str:
        return self._gather_stacks_edge

    @gather_stacks_edge.setter
    def gather_stacks_edge(self, value: str) -> None:
        self._gather_stacks_edge = value
        if self._backing is not None:
            self._backing.setValue(_KEY_GATHER_STACKS_EDGE, value)

    @property
    def view_on_open(self) -> str:
        return self._view_on_open

    @view_on_open.setter
    def view_on_open(self, value: str) -> None:
        self._view_on_open = value
        if self._backing is not None:
            self._backing.setValue(_KEY_VIEW_ON_OPEN, value)
