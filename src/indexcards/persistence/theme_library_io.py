from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QStandardPaths

from indexcards.models.theme import Theme

DEFAULT_LIBRARY_FILENAME = "custom_themes.json"
_LIBRARY_SCHEMA_VERSION = 1


def library_path() -> Path:
    app_data_dir = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppDataLocation
    )
    return Path(app_data_dir) / DEFAULT_LIBRARY_FILENAME


def load_custom_themes(path: Path) -> list[Theme]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Theme.from_dict(theme_data) for theme_data in data.get("themes", [])]


def save_custom_themes(themes: list[Theme], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": _LIBRARY_SCHEMA_VERSION,
        "themes": [theme.to_dict() for theme in themes],
    }
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")
