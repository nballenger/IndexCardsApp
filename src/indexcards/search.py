from __future__ import annotations

from indexcards.models.card import Card


def matches(card: Card, query: str) -> bool:
    """Case-insensitive substring match against a card's text or any tag."""
    if not query:
        return True
    query_lower = query.lower()
    if query_lower in card.text.lower():
        return True
    return any(query_lower in tag.lower() for tag in card.tags)
