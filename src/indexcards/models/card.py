from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from indexcards.models.palette import DEFAULT_COLOR

DEFAULT_CARD_SIZE = (200, 120)  # 5:3, matching a real 5x3 index card
MAX_TEXT_LENGTH = 160


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class Card:
    id: str
    text: str = ""
    x: float = 0.0
    y: float = 0.0
    color: str = DEFAULT_COLOR
    tags: list[str] = field(default_factory=list)
    pinned: bool = False
    created_at: str = field(default_factory=_now)
    modified_at: str = field(default_factory=_now)
