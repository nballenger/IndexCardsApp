from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ThemeOrigin = Literal["preset", "custom"]


@dataclass
class Slot:
    id: str
    label: str
    hex: str
    text_color: str | None = None
    orphaned: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "hex": self.hex,
            "text_color": self.text_color,
            "orphaned": self.orphaned,
        }

    @staticmethod
    def from_dict(data: dict) -> Slot:
        return Slot(
            id=data["id"],
            label=data.get("label", ""),
            hex=data["hex"],
            text_color=data.get("text_color"),
            orphaned=data.get("orphaned", False),
        )


@dataclass
class Theme:
    id: str
    name: str
    origin: ThemeOrigin
    background_color: str
    slots: list[Slot] = field(default_factory=list)

    def get_slot(self, slot_id: str) -> Slot | None:
        for slot in self.slots:
            if slot.id == slot_id:
                return slot
        return None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "origin": self.origin,
            "background_color": self.background_color,
            "slots": [slot.to_dict() for slot in self.slots],
        }

    @staticmethod
    def from_dict(data: dict) -> Theme:
        return Theme(
            id=data["id"],
            name=data.get("name", ""),
            origin=data.get("origin", "custom"),
            background_color=data["background_color"],
            slots=[Slot.from_dict(slot_data) for slot_data in data.get("slots", [])],
        )


def clone_theme(theme: Theme) -> Theme:
    """Independent deep copy preserving id/name/origin/slot ids — gives a
    Document its own embedded snapshot without minting a new identity
    (round-trips through to_dict/from_dict rather than copy.deepcopy so
    there's exactly one place that defines what "a full copy" means)."""
    return Theme.from_dict(theme.to_dict())


def duplicate_theme(theme: Theme, new_id: str, new_name: str) -> Theme:
    """A brand-new custom theme deep-copied from theme, with a fresh
    id/name and origin='custom'. Slot ids are preserved from the source,
    so a document already using `theme` produces zero orphans if it later
    switches to this duplicate."""
    copy = clone_theme(theme)
    copy.id = new_id
    copy.name = new_name
    copy.origin = "custom"
    return copy
