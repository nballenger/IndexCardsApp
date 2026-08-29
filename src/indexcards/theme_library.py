from __future__ import annotations

from pathlib import Path

from indexcards.models.theme import Theme
from indexcards.persistence.theme_library_io import load_custom_themes, save_custom_themes


class ThemeLibrary:
    """The app-level, cross-document collection of user-created custom
    themes — persisted to its own file, unlike a document's own embedded
    theme snapshot which is private to that one file.

    path=None (the default, and what every test construction uses) keeps
    the library purely in memory so tests never touch the developer's
    real custom-themes file; only app.py's production entry point
    supplies a real path (theme_library_io.library_path()).
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._themes: dict[str, Theme] = {}
        if path is not None and path.exists():
            for theme in load_custom_themes(path):
                self._themes[theme.id] = theme

    def all(self) -> list[Theme]:
        return list(self._themes.values())

    def get(self, theme_id: str) -> Theme | None:
        return self._themes.get(theme_id)

    def add(self, theme: Theme) -> None:
        self._themes[theme.id] = theme
        self._save()

    def update(self, theme: Theme) -> None:
        self._themes[theme.id] = theme
        self._save()

    def remove(self, theme_id: str) -> None:
        self._themes.pop(theme_id, None)
        self._save()

    def _save(self) -> None:
        if self._path is not None:
            save_custom_themes(list(self._themes.values()), self._path)
