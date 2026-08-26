from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class Stack:
    id: str
    card_ids: list[str] = field(default_factory=list)
    x: float = 0.0
    y: float = 0.0
    label: str = ""
    created_at: str = field(default_factory=_now)
    modified_at: str = field(default_factory=_now)
