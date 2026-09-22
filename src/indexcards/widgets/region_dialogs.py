from __future__ import annotations

from PySide6.QtWidgets import QInputDialog, QWidget


def prompt_region_label(parent: QWidget | None, title: str, initial: str) -> str | None:
    """QInputDialog.getText wrapper for naming/renaming a region -- returns
    the stripped text, or None if the user cancelled."""
    text, ok = QInputDialog.getText(parent, title, "Label:", text=initial)
    if not ok:
        return None
    return text.strip()
