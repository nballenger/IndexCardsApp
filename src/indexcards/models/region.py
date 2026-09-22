from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

MIN_REGION_SIZE = (240.0, 160.0)  # a card plus buffer, room for the label bar
DEFAULT_REGION_SIZE = (360.0, 220.0)


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class Region:
    id: str
    x: float = 0.0
    y: float = 0.0
    width: float = DEFAULT_REGION_SIZE[0]
    height: float = DEFAULT_REGION_SIZE[1]
    label: str = ""
    created_at: str = field(default_factory=_now)
    modified_at: str = field(default_factory=_now)
