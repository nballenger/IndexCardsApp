from __future__ import annotations

import json
from pathlib import Path

from indexcards.models.document import Document
from indexcards.persistence.migrations import migrate
from indexcards.persistence.serializer import from_dict, to_dict


def save_document(document: Document, path: Path) -> None:
    data = to_dict(document)
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    Path(path).write_text(text, encoding="utf-8")
    document.mark_clean()


def load_document(path: Path) -> Document:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data = migrate(data)
    return from_dict(data)
