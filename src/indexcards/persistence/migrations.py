from __future__ import annotations

from indexcards.models.document import DEFAULT_CANVAS_BACKGROUND_COLOR

CURRENT_SCHEMA_VERSION = 2


def _migrate_v1_to_v2(data: dict) -> dict:
    data = dict(data)
    data["schema_version"] = 2
    file_meta = dict(data.get("file", {}))
    file_meta.setdefault("canvas_background_color", DEFAULT_CANVAS_BACKGROUND_COLOR)
    data["file"] = file_meta
    return data


# Each entry maps a schema_version to the function that upgrades a raw dict
# from that version to version + 1. Applied in a loop by migrate() until the
# data reaches CURRENT_SCHEMA_VERSION.
_MIGRATIONS: dict[int, callable] = {1: _migrate_v1_to_v2}


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
