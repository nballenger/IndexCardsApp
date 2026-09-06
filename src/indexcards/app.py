from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from indexcards.app_settings import AppSettings
from indexcards.persistence.file_io import load_document
from indexcards.persistence.theme_library_io import library_path
from indexcards.theme_library import ThemeLibrary
from indexcards.window_manager import WindowManager


def _validate_paths(paths: list[Path]) -> int:
    """Headless equivalent of opening each path in the app, for an agent to
    check its own generated output without a GUI: loads (and, same as a
    real open, repairs) each file via the normal load_document() path, with
    no WindowManager/window ever created. Prints one line per issue found.
    Exit status treats "loaded but something needed repair" as a failure,
    not just a hard load error -- the bar here is "authored correctly," not
    merely "the app would tolerate it."""
    all_clean = True
    for path in paths:
        try:
            document = load_document(path)
        except (OSError, ValueError) as exc:
            print(f"FAIL: {path}: {exc}")
            all_clean = False
            continue
        if document.load_warnings:
            print(f"FAIL: {path}")
            for message in document.load_warnings:
                print(f"  - {message}")
            all_clean = False
        else:
            print(f"OK: {path}")
    return 0 if all_clean else 1


def main() -> None:
    app = QApplication(sys.argv)
    app.setOrganizationName("nballenger")
    app.setApplicationName("IndexCards")
    # app.arguments() (Qt's own parsed argv, [0] is the program name) over
    # bare sys.argv — Qt strips any of its own recognized flags first, and
    # this is the same list QApplication itself already consumed.
    args = app.arguments()[1:]
    if "--validate" in args:
        sys.exit(_validate_paths([Path(arg) for arg in args if arg != "--validate"]))
    window_manager = WindowManager(
        settings=AppSettings(QSettings()), theme_library=ThemeLibrary(library_path())
    )
    # Each positional argument is a file to open, one window per file, so
    # `indexcards a.idxcards b.idxcards` opens both at once — bad paths
    # each surface their own "Failed to Open File" dialog (same as File >
    # Open) rather than aborting the rest.
    paths = [Path(arg) for arg in args]
    if paths:
        for path in paths:
            window_manager.open_file(path)
    else:
        window_manager.open_new_window()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
