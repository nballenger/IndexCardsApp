from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class Link:
    id: str
    source: str
    target: str
    label: str = ""
    created_at: str = field(default_factory=_now)
