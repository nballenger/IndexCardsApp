from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from indexcards.window_manager import WindowManager


def main() -> None:
    app = QApplication(sys.argv)
    window_manager = WindowManager()
    window_manager.open_new_window()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
