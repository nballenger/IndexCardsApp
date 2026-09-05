from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


LINE_ENDING_OPTIONS: list[tuple[str, str]] = [
    ("none", "No arrows"),
    ("to_target", "Arrow to Target"),
    ("to_source", "Arrow to Source"),
    ("both", "Double-Ended"),
]


@dataclass
class Link:
    id: str
    source: str
    target: str
    label: str = ""
    line_ending: str = "none"
    created_at: str = field(default_factory=_now)
