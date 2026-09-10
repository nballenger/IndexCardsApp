from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

DEFAULT_CARD_SIZE = (200, 120)  # 5:3, matching a real 5x3 index card
# Empirically measured (not a round guess): the most realistic wrapping
# prose that canvas/text_fit.fit_text_to_area can still shrink to fit the
# card's text area, at the app's default minimum font size (9pt) -- so a
# card can now fill all the way up before hitting this wall, rather than
# being blocked well short of what adaptive shrinking can actually fit.
MAX_TEXT_LENGTH = 560
DEFAULT_COLOR_SLOT_ID = "slot_white"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class Card:
    id: str
    text: str = ""
    x: float = 0.0
    y: float = 0.0
    color_slot: str = DEFAULT_COLOR_SLOT_ID
    tags: list[str] = field(default_factory=list)
    pinned: bool = False
    stack_id: str | None = None
    created_at: str = field(default_factory=_now)
    modified_at: str = field(default_factory=_now)
