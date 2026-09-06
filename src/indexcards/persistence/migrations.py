from __future__ import annotations

from indexcards.models.document import DEFAULT_CANVAS_BACKGROUND_COLOR
from indexcards.models.palette import PALETTE

CURRENT_SCHEMA_VERSION = 9


def _migrate_v1_to_v2(data: dict) -> dict:
    data = dict(data)
    data["schema_version"] = 2
    file_meta = dict(data.get("file", {}))
    file_meta.setdefault("canvas_background_color", DEFAULT_CANVAS_BACKGROUND_COLOR)
    data["file"] = file_meta
    return data


def _migrate_v2_to_v3(data: dict) -> dict:
    data = dict(data)
    data["schema_version"] = 3
    data["cards"] = [{"pinned": False, **card} for card in data.get("cards", [])]
    return data


def _migrate_v3_to_v4(data: dict) -> dict:
    data = dict(data)
    data["schema_version"] = 4
    data["cards"] = [{"stack_id": None, **card} for card in data.get("cards", [])]
    data["stacks"] = data.get("stacks", [])
    return data


def _slot_id_for_palette_name(name: str) -> str:
    return f"slot_{name.lower()}"


def _migrate_v4_to_v5(data: dict) -> dict:
    """Introduces the theme/slot color model, replacing the flat global
    PALETTE. Builds a single "Classic" theme from today's PALETTE (using
    the file's own background color), then rewrites every card's literal
    `color` hex into a `color_slot` reference into that theme. A hex that
    isn't one of PALETTE's own values (possible today since `color` was
    never validated against PALETTE) is preserved losslessly as its own
    orphaned slot rather than silently collapsed to a default, resolvable
    later via the ordinary orphan-resolution flow."""
    data = dict(data)
    data["schema_version"] = 5

    file_meta = dict(data.get("file", {}))
    old_background = file_meta.pop("canvas_background_color", DEFAULT_CANVAS_BACKGROUND_COLOR)
    data["file"] = file_meta

    slots = [
        {
            "id": _slot_id_for_palette_name(name),
            "label": name,
            "hex": hex_value,
            "text_color": None,
            "orphaned": False,
        }
        for name, hex_value in PALETTE.items()
    ]
    hex_to_slot_id = {slot["hex"].lower(): slot["id"] for slot in slots}

    migrated_cards = []
    for card in data.get("cards", []):
        card = dict(card)
        old_hex = card.pop("color", PALETTE["White"])
        slot_id = hex_to_slot_id.get(old_hex.lower())
        if slot_id is None:
            slot_id = f"slot_custom_{old_hex.lstrip('#').lower()}"
            if slot_id not in {slot["id"] for slot in slots}:
                slots.append(
                    {
                        "id": slot_id,
                        "label": old_hex,
                        "hex": old_hex,
                        "text_color": None,
                        "orphaned": True,
                    }
                )
            hex_to_slot_id[old_hex.lower()] = slot_id
        card["color_slot"] = slot_id
        migrated_cards.append(card)

    data["theme"] = {
        "id": "preset_classic",
        "name": "Classic",
        "origin": "preset",
        "background_color": old_background,
        "slots": slots,
    }
    data["cards"] = migrated_cards
    data.setdefault("color_key_visible", False)
    return data


def _migrate_v5_to_v6(data: dict) -> dict:
    """Introduces theme-level link styling (color + line weight). Every
    default here matches what LinkItem already rendered before this field
    existed (Qt's darkGray, i.e. "#808080", at 2px) so migrating an
    existing file produces zero visual change."""
    data = dict(data)
    data["schema_version"] = 6
    theme = dict(data.get("theme", {}))
    theme.setdefault("link_color", "#808080")
    theme.setdefault("link_color_mode", "theme")
    theme.setdefault("link_weight", 2)
    data["theme"] = theme
    return data


def _migrate_v6_to_v7(data: dict) -> dict:
    """Introduces per-link line-ending styling (arrowheads). Every
    existing link defaults to "none", preserving today's plain-line
    look."""
    data = dict(data)
    data["schema_version"] = 7
    data["links"] = [{"line_ending": "none", **link} for link in data.get("links", [])]
    return data


def _migrate_v7_to_v8(data: dict) -> dict:
    """Introduces a document-level default line-ending for newly-created
    links. Existing files get "none", matching what every link created
    before this feature existed would have used."""
    data = dict(data)
    data["schema_version"] = 8
    data.setdefault("default_line_ending", "none")
    return data


def _migrate_v8_to_v9(data: dict) -> dict:
    """Introduces per-document saved view state (zoom + pan center) for
    the "View from last save" open-behavior setting. Every existing file
    has none yet -- None signals "fall back to Zoom Extents" on open."""
    data = dict(data)
    data["schema_version"] = 9
    data.setdefault("view_zoom", None)
    data.setdefault("view_center_x", None)
    data.setdefault("view_center_y", None)
    return data


# Each entry maps a schema_version to the function that upgrades a raw dict
# from that version to version + 1. Applied in a loop by migrate() until the
# data reaches CURRENT_SCHEMA_VERSION.
_MIGRATIONS: dict[int, callable] = {
    1: _migrate_v1_to_v2,
    2: _migrate_v2_to_v3,
    3: _migrate_v3_to_v4,
    4: _migrate_v4_to_v5,
    5: _migrate_v5_to_v6,
    6: _migrate_v6_to_v7,
    7: _migrate_v7_to_v8,
    8: _migrate_v8_to_v9,
}


def migrate(data: dict) -> dict:
    version = data.get("schema_version", 1)
    if version > CURRENT_SCHEMA_VERSION:
        raise ValueError(
            f"file schema_version {version} is newer than this app supports "
            f"(supports up to {CURRENT_SCHEMA_VERSION})"
        )
    while version < CURRENT_SCHEMA_VERSION:
        upgrade = _MIGRATIONS[version]
        data = upgrade(data)
        version = data["schema_version"]
    return data
