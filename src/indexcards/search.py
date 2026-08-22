from __future__ import annotations

from indexcards.feature_flags import TAGS_ENABLED
from indexcards.models.card import Card


def matches(card: Card, query: str) -> bool:
    """Case-insensitive substring match against a card's text (and tags,
    when TAGS_ENABLED)."""
    if not query:
        return True
    query_lower = query.lower()
    if query_lower in card.text.lower():
        return True
    if not TAGS_ENABLED:
        return False
    return any(query_lower in tag.lower() for tag in card.tags)
