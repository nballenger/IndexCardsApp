from __future__ import annotations

import sys

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from indexcards.app_settings import AppSettings
from indexcards.window_manager import WindowManager


def main() -> None:
    app = QApplication(sys.argv)
    app.setOrganizationName("nballenger")
    app.setApplicationName("IndexCards")
    window_manager = WindowManager(settings=AppSettings(QSettings()))
    window_manager.open_new_window()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
