from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from indexcards.app_settings import AppSettings
from indexcards.persistence.theme_library_io import library_path
from indexcards.theme_library import ThemeLibrary
from indexcards.window_manager import WindowManager


def main() -> None:
    app = QApplication(sys.argv)
    app.setOrganizationName("nballenger")
    app.setApplicationName("IndexCards")
    window_manager = WindowManager(
        settings=AppSettings(QSettings()), theme_library=ThemeLibrary(library_path())
    )
    # app.arguments() (Qt's own parsed argv, [0] is the program name) over
    # bare sys.argv — Qt strips any of its own recognized flags first, and
    # this is the same list QApplication itself already consumed. Each
    # positional argument is a file to open, one window per file, so
    # `indexcards a.idxcards b.idxcards` opens both at once — bad paths
    # each surface their own "Failed to Open File" dialog (same as File >
    # Open) rather than aborting the rest.
    paths = [Path(arg) for arg in app.arguments()[1:]]
    if paths:
        for path in paths:
            window_manager.open_file(path)
    else:
        window_manager.open_new_window()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
