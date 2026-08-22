from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QUndoGroup

from indexcards.app_settings import AppSettings
from indexcards.main_window import MainWindow


class WindowManager:
    """Tracks open MainWindows (one window per file) and the QUndoGroup and
    AppSettings shared across them, so Undo/Redo always targets the focused
    window and preferences are the same everywhere.

    settings=None (the default) falls back to an in-memory-only
    AppSettings, the same "safe standalone construction" pattern already
    used for undo_group's QUndoGroup(self) fallback in MainWindow — real
    persistence is opted into explicitly by app.py, the one production
    entry point.
    """

    def __init__(self, settings: AppSettings | None = None) -> None:
        self.undo_group = QUndoGroup()
        self.settings = settings if settings is not None else AppSettings()
        self._windows: list[MainWindow] = []

    def open_new_window(self) -> MainWindow:
        window = MainWindow(self)
        self._windows.append(window)
        window.show()
        return window

    def open_file(self, path: Path, requesting_window: MainWindow | None = None) -> MainWindow:
        """Opens path, preferring — in order — an already-open window on
        that file (focused rather than duplicated), then requesting_window
        if it's a blank untouched window (reused rather than left stranded
        as an extra empty window), then a freshly created window."""
        existing = self._find_window_for_path(path)
        if existing is not None:
            existing.raise_()
            existing.activateWindow()
            return existing

        if requesting_window is not None and requesting_window.is_reusable():
            requesting_window.open_file(path)
            return requesting_window

        window = MainWindow(self)
        self._windows.append(window)
        window.open_file(path)
        window.show()
        return window

    def forget_window(self, window: MainWindow) -> None:
        if window in self._windows:
            self._windows.remove(window)

    def _find_window_for_path(self, path: Path) -> MainWindow | None:
        target = path.resolve()
        for window in self._windows:
            window_path = window.current_path
            if window_path is not None and window_path.resolve() == target:
                return window
        return None
