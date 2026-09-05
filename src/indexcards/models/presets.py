from __future__ import annotations

from indexcards.models.palette import PALETTE
from indexcards.models.theme import Slot, Theme

# Deliberately not imported from models/document.py's
# DEFAULT_CANVAS_BACKGROUND_COLOR: document.py's default Document
# construction depends on PRESET_THEMES, so this module must not depend on
# document.py in the other direction. Kept in sync by convention rather
# than a shared import.
_CLASSIC_BACKGROUND_COLOR = "#3d6b4f"


def _build_classic_preset() -> Theme:
    """The original 7-color palette this app shipped with before themes
    existed. Slot ids (`slot_<lowercased name>`) must never change — the
    v4->v5 migration (persistence/migrations.py) builds identical ids for
    every pre-existing document, so this theme's identity is load-bearing
    for old files, not just cosmetic."""
    return Theme(
        id="preset_classic",
        name="Classic",
        origin="preset",
        background_color=_CLASSIC_BACKGROUND_COLOR,
        link_color="#808080",
        link_color_mode="theme",
        link_weight=2,
        slots=[
            Slot(id=f"slot_{name.lower()}", label=name, hex=hex_value)
            for name, hex_value in PALETTE.items()
        ],
    )


def _build_vivid_preset() -> Theme:
    """Bolder, more saturated colors for a board that wants color to
    carry real signal, on a dark neutral canvas."""
    return Theme(
        id="preset_vivid",
        name="Vivid",
        origin="preset",
        background_color="#1F2733",
        link_color="#808080",
        link_color_mode="theme",
        link_weight=2,
        slots=[
            Slot(id="vivid_red", label="Red", hex="#E76F51"),
            Slot(id="vivid_orange", label="Orange", hex="#F4A261"),
            Slot(id="vivid_yellow", label="Yellow", hex="#E9C46A"),
            Slot(id="vivid_green", label="Green", hex="#8AB17D"),
            Slot(id="vivid_teal", label="Teal", hex="#2A9D8F"),
            Slot(id="vivid_blue", label="Blue", hex="#5B8FB9"),
            Slot(id="vivid_purple", label="Purple", hex="#9B7FB8"),
        ],
    )


def _build_midnight_preset() -> Theme:
    """Deep, muted jewel tones for a true dark-mode board — cards read
    like softly lit panels on black, not bright cutouts."""
    return Theme(
        id="preset_midnight",
        name="Midnight",
        origin="preset",
        background_color="#121212",
        link_color="#808080",
        link_color_mode="theme",
        link_weight=2,
        slots=[
            Slot(id="midnight_ruby", label="Ruby", hex="#7A2E3B"),
            Slot(id="midnight_amber", label="Amber", hex="#8A5A2B"),
            Slot(id="midnight_olive", label="Olive", hex="#5C6B2E"),
            Slot(id="midnight_teal", label="Teal", hex="#245C5A"),
            Slot(id="midnight_indigo", label="Indigo", hex="#33406B"),
            Slot(id="midnight_plum", label="Plum", hex="#5A3768"),
            Slot(id="midnight_slate", label="Slate", hex="#3D4450"),
        ],
    )


def _build_accessible_preset() -> Theme:
    """The Okabe-Ito palette, engineered to stay distinguishable under the
    most common forms of color blindness, on a light canvas."""
    return Theme(
        id="preset_accessible",
        name="Accessible",
        origin="preset",
        background_color="#F4F3EE",
        link_color="#808080",
        link_color_mode="theme",
        link_weight=2,
        slots=[
            Slot(id="accessible_orange", label="Orange", hex="#E69F00"),
            Slot(id="accessible_sky_blue", label="Sky Blue", hex="#56B4E9"),
            Slot(id="accessible_bluish_green", label="Bluish Green", hex="#009E73"),
            Slot(id="accessible_yellow", label="Yellow", hex="#F0E442"),
            Slot(id="accessible_blue", label="Blue", hex="#0072B2"),
            Slot(id="accessible_vermillion", label="Vermillion", hex="#D55E00"),
            Slot(id="accessible_reddish_purple", label="Reddish Purple", hex="#CC79A7"),
        ],
    )


PRESET_THEMES: list[Theme] = [
    _build_classic_preset(),
    _build_vivid_preset(),
    _build_midnight_preset(),
    _build_accessible_preset(),
]


def get_preset_theme(theme_id: str) -> Theme | None:
    for theme in PRESET_THEMES:
        if theme.id == theme_id:
            return theme
    return None
