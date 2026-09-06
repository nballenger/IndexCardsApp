from __future__ import annotations

import json
from pathlib import Path

from indexcards.models.document import Document
from indexcards.persistence.migrations import migrate
from indexcards.persistence.serializer import from_dict, to_dict
from indexcards.persistence.validation import repair_document


def save_document(document: Document, path: Path) -> None:
    data = to_dict(document)
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    Path(path).write_text(text, encoding="utf-8")
    document.mark_clean()


def load_document(path: Path) -> Document:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    try:
        data = migrate(data)
        document = from_dict(data)
    except (KeyError, TypeError, AttributeError) as exc:
        # Valid JSON but the wrong shape (missing a required field, a list
        # where an object was expected, etc.) — surfaced as ValueError so
        # callers can handle it the same way as malformed JSON itself
        # (json.JSONDecodeError is already a ValueError) rather than
        # crashing on whatever built-in exception the bad shape happened
        # to trigger.
        raise ValueError(f"'{Path(path).name}' is not a valid Index Cards file: {exc}") from exc
    # Repairs a dangling color_slot/link/stack reference (e.g. from a
    # hand-authored file) rather than crashing on it later mid-render — see
    # persistence.validation.repair_document's own docstring for why this
    # runs here, once, rather than being folded into from_dict() itself.
    document.load_warnings = repair_document(document)
    return document
