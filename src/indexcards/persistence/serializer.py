from __future__ import annotations

from indexcards.models.card import Card
from indexcards.models.document import DEFAULT_CANVAS_BACKGROUND_COLOR, Document
from indexcards.models.link import Link
from indexcards.models.stack import Stack
from indexcards.persistence.migrations import CURRENT_SCHEMA_VERSION

APP_VERSION = "0.1.0"


def to_dict(document: Document) -> dict:
    return {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "app_version": APP_VERSION,
        "file": {
            "name": document.name,
            "created_at": document.created_at,
            "modified_at": document.modified_at,
            "canvas_background_color": document.canvas_background_color,
        },
        "cards": [
            {
                "id": card.id,
                "text": card.text,
                "position": {"x": card.x, "y": card.y},
                "color": card.color,
                "tags": list(card.tags),
                "pinned": card.pinned,
                "stack_id": card.stack_id,
                "created_at": card.created_at,
                "modified_at": card.modified_at,
            }
            for card in document.iter_cards()
        ],
        "links": [
            {
                "id": link.id,
                "source": link.source,
                "target": link.target,
                "label": link.label,
                "created_at": link.created_at,
            }
            for link in document.iter_links()
        ],
        "stacks": [
            {
                "id": stack.id,
                "card_ids": list(stack.card_ids),
                "position": {"x": stack.x, "y": stack.y},
                "label": stack.label,
                "created_at": stack.created_at,
                "modified_at": stack.modified_at,
            }
            for stack in document.iter_stacks()
        ],
    }


def from_dict(data: dict) -> Document:
    file_meta = data.get("file", {})
    document = Document(name=file_meta.get("name", "Untitled"))
    document.created_at = file_meta.get("created_at", document.created_at)
    document.modified_at = file_meta.get("modified_at", document.modified_at)
    document.canvas_background_color = file_meta.get(
        "canvas_background_color", DEFAULT_CANVAS_BACKGROUND_COLOR
    )

    for card_data in data.get("cards", []):
        position = card_data.get("position", {})
        card = Card(
            id=card_data["id"],
            text=card_data.get("text", ""),
            x=position.get("x", 0.0),
            y=position.get("y", 0.0),
            color=card_data.get("color", Card.color),
            tags=list(card_data.get("tags", [])),
            pinned=card_data.get("pinned", False),
            stack_id=card_data.get("stack_id"),
            created_at=card_data.get("created_at", ""),
            modified_at=card_data.get("modified_at", ""),
        )
        document.cards[card.id] = card

    for stack_data in data.get("stacks", []):
        position = stack_data.get("position", {})
        stack = Stack(
            id=stack_data["id"],
            card_ids=list(stack_data.get("card_ids", [])),
            x=position.get("x", 0.0),
            y=position.get("y", 0.0),
            label=stack_data.get("label", ""),
            created_at=stack_data.get("created_at", ""),
            modified_at=stack_data.get("modified_at", ""),
        )
        document.stacks[stack.id] = stack

    for link_data in data.get("links", []):
        link = Link(
            id=link_data["id"],
            source=link_data["source"],
            target=link_data["target"],
            label=link_data.get("label", ""),
            created_at=link_data.get("created_at", ""),
        )
        if link.source not in document.cards or link.target not in document.cards:
            raise ValueError(
                f"link {link.id!r} references a nonexistent card "
                f"(source={link.source!r}, target={link.target!r})"
            )
        document.links[link.id] = link

    document.mark_clean()
    return document
