from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Reference:
    text: str = ""
    url: str = ""

    def to_dict(self) -> dict:
        return {"text": self.text, "url": self.url}

    @staticmethod
    def from_dict(data: dict) -> Reference:
        return Reference(text=data.get("text", ""), url=data.get("url", ""))
