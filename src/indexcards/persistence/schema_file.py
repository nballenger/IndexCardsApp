from __future__ import annotations

from importlib.resources import files


def schema_text() -> str:
    """The JSON Schema for .idxcards files, read as a package resource so it
    resolves the same way from a checkout, an installed wheel, and the
    PyInstaller app bundle (see the datas entry in IndexCards.spec)."""
    return (
        files("indexcards.persistence")
        .joinpath("idxcards.schema.json")
        .read_text(encoding="utf-8")
    )
