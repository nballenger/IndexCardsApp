from __future__ import annotations

from indexcards.models.palette import PALETTE
from indexcards.models.theme import Slot, Theme

# Deliberately not imported from models/document.py's
# DEFAULT_CANVAS_BACKGROUND_COLOR: document.py's default Document
# construction will need to depend on PRESET_THEMES (M2), so this module
# must not depend on document.py in the other direction. Kept in sync by
# convention rather than a shared import.
_PLACEHOLDER_PRESET_BACKGROUND_COLOR = "#3d6b4f"


def _build_placeholder_preset() -> Theme:
    """One preset built directly from today's flat PALETTE, standing in
    until real preset themes are designed (explicitly deferred)."""
    return Theme(
        id="preset_classic",
        name="Classic",
        origin="preset",
        background_color=_PLACEHOLDER_PRESET_BACKGROUND_COLOR,
        slots=[
            Slot(id=f"slot_{name.lower()}", label=name, hex=hex_value)
            for name, hex_value in PALETTE.items()
        ],
    )


PRESET_THEMES: list[Theme] = [_build_placeholder_preset()]


def get_preset_theme(theme_id: str) -> Theme | None:
    for theme in PRESET_THEMES:
        if theme.id == theme_id:
            return theme
    return None
