from __future__ import annotations

import uuid
from collections.abc import Iterable


def _new_id(prefix: str, existing_ids: Iterable[str]) -> str:
    existing = set(existing_ids)
    while True:
        candidate = f"{prefix}_{uuid.uuid4().hex[:8]}"
        if candidate not in existing:
            return candidate


def new_card_id(existing_ids: Iterable[str] = ()) -> str:
    return _new_id("c", existing_ids)


def new_link_id(existing_ids: Iterable[str] = ()) -> str:
    return _new_id("l", existing_ids)
