from __future__ import annotations

CURRENT_SCHEMA_VERSION = 1

# Each entry maps a schema_version to the function that upgrades a raw dict
# from that version to version + 1. Applied in a loop by migrate() until the
# data reaches CURRENT_SCHEMA_VERSION. Empty for now since v1 is the only
# schema that has ever existed.
_MIGRATIONS: dict[int, callable] = {}


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
