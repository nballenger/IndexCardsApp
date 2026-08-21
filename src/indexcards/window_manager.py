from __future__ import annotations

from PySide6.QtGui import QUndoGroup

from indexcards.main_window import MainWindow


class WindowManager:
    """Tracks open MainWindows and the shared QUndoGroup across them."""

    def __init__(self) -> None:
        self.undo_group = QUndoGroup()
        self._windows: list[MainWindow] = []

    def open_new_window(self) -> MainWindow:
        window = MainWindow(undo_group=self.undo_group)
        self._windows.append(window)
        window.show()
        return window
