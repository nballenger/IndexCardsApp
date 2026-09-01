from __future__ import annotations

from collections.abc import Callable

from indexcards.models.card import MAX_TEXT_LENGTH, Card
from indexcards.models.document import Document
from indexcards.models.stack import Stack
from indexcards.models.theme import Theme
from indexcards.utils.ids import new_card_id, new_stack_id

CLIPBOARD_MIME_TYPE = "application/x-indexcards-selection+json"
CLIPBOARD_FORMAT_VERSION = 1


def _card_to_dict(card: Card, document: Document) -> dict:
    slot = document.get_slot(card.color_slot)
    return {
        "text": card.text,
        "x": card.x,
        "y": card.y,
        "tags": list(card.tags),
        "color_hex": slot.hex,
        "color_label": slot.label,
    }


def build_clipboard_payload(document: Document, card_ids: list[str], stack_ids: list[str]) -> dict:
    """A JSON-able snapshot of the given loose cards and stacks (each
    carrying its own member cards, in stack order). Color is captured as
    hex/label rather than the source document's theme-local color_slot
    id, since that id has no meaning in a different document/theme."""
    cards = [_card_to_dict(document.get_card(card_id), document) for card_id in card_ids]
    stacks = []
    for stack_id in stack_ids:
        stack = document.get_stack(stack_id)
        stacks.append(
            {
                "label": stack.label,
                "x": stack.x,
                "y": stack.y,
                "cards": [
                    _card_to_dict(document.get_card(member_id), document)
                    for member_id in stack.card_ids
                ],
            }
        )
    return {"version": CLIPBOARD_FORMAT_VERSION, "cards": cards, "stacks": stacks}


STACK_HEADER_PREFIX = "IndexCards Stack: "
STACK_BULLET_PREFIX = "* "


def _escape_newlines(text: str) -> str:
    """Plain text has no way to tell "a newline inside one card's text"
    apart from "the boundary between two different cards" — so a card's
    own newlines are escaped to a literal two-character \\n, keeping
    exactly one physical line per card. See _unescape_newlines for the
    other half of this round trip."""
    return text.replace("\n", "\\n")


def _unescape_newlines(text: str) -> str:
    return text.replace("\\n", "\n")


def plain_text_for_payload(
    payload: dict, normalize_text: Callable[[str], str] = lambda text: text
) -> str:
    """One physical line per card (its own newlines escaped as literal
    \\n — see _escape_newlines): every loose card's text, then each
    stack as an "IndexCards Stack: <label>" header line followed by a
    "* "-prefixed line per member card, in stack order. The header/
    bullet formatting is one-way (for reading in another app) — pasting
    it back into IndexCards degrades to loose cards, stripped of the
    header and bullet prefix (see card_texts_from_plain_text); only the
    internal MIME payload round-trips a stack as a real Stack.

    normalize_text runs on each card's raw stored text before escaping —
    a card's text is itself markdown (see main_window._card_text_to_
    logical), where a hard line break is a blank-line block separator,
    not a single \\n; escaping that verbatim would double every break.
    Defaults to identity so this module stays Qt-free and independently
    testable; the real caller injects the markdown-aware normalizer.
    """
    lines = [_escape_newlines(normalize_text(card["text"])) for card in payload.get("cards", [])]
    for stack in payload.get("stacks", []):
        lines.append(f"{STACK_HEADER_PREFIX}{stack.get('label', '')}")
        lines.extend(
            f"{STACK_BULLET_PREFIX}{_escape_newlines(normalize_text(card['text']))}"
            for card in stack.get("cards", [])
        )
    return "\n".join(lines)


def resolve_color_slot(theme: Theme, color_hex: str, color_label: str) -> str:
    """Case-insensitive hex match against theme.slots; falls back to
    theme.slots[0].id (the same "first slot is default" convention
    already used at every existing card-creation call site)."""
    del color_label  # not currently used for matching, kept for future use/debugging
    hex_lower = color_hex.lower()
    for slot in theme.slots:
        if slot.hex.lower() == hex_lower:
            return slot.id
    return theme.slots[0].id


def _build_card(card_data: dict, theme: Theme, existing_ids: set[str]) -> Card:
    card_id = new_card_id(existing_ids)
    existing_ids.add(card_id)
    color_slot = resolve_color_slot(
        theme, card_data["color_hex"], card_data.get("color_label", "")
    )
    return Card(
        id=card_id,
        text=card_data["text"],
        x=card_data["x"],
        y=card_data["y"],
        color_slot=color_slot,
        tags=list(card_data.get("tags", [])),
    )


def cards_and_stacks_from_payload(
    payload: dict, theme: Theme, existing_ids: set[str]
) -> tuple[list[Card], list[tuple[Stack, list[Card]]]]:
    """Builds brand-new Card/Stack objects (fresh ids, never colliding
    with existing_ids) from a payload previously produced by
    build_clipboard_payload. Raises ValueError if payload isn't a
    recognizable clipboard payload of this format/version — callers
    should treat that as "not our format," not a hard error.

    existing_ids is mutated (ids generated along the way are added to it
    immediately) so a batch of many new cards/stacks can never collide
    with each other, not just with what was already in the document.
    """
    try:
        if payload.get("version") != CLIPBOARD_FORMAT_VERSION:
            raise ValueError(f"unsupported clipboard payload version: {payload.get('version')!r}")
        cards = [_build_card(card_data, theme, existing_ids) for card_data in payload["cards"]]
        stacks: list[tuple[Stack, list[Card]]] = []
        for stack_data in payload["stacks"]:
            stack_id = new_stack_id(existing_ids)
            existing_ids.add(stack_id)
            members = [
                _build_card(card_data, theme, existing_ids) for card_data in stack_data["cards"]
            ]
            for member in members:
                member.stack_id = stack_id
            stack = Stack(
                id=stack_id,
                card_ids=[member.id for member in members],
                x=stack_data["x"],
                y=stack_data["y"],
                label=stack_data.get("label", ""),
            )
            stacks.append((stack, members))
    except (KeyError, TypeError) as exc:
        raise ValueError(f"not a valid IndexCards clipboard payload: {exc}") from exc
    return cards, stacks


def card_texts_from_plain_text(
    text: str, denormalize_text: Callable[[str], str] = lambda text: text
) -> list[str]:
    """Splits on newlines, strips, drops empty lines, unescapes a literal
    \\n back into a real newline (the inverse of plain_text_for_payload's
    _escape_newlines — this is what lets a card round-tripped through
    another app reconstruct its own embedded newlines rather than
    splitting into one card per line), truncates to Card.MAX_TEXT_LENGTH
    — one entry per new card an external-app paste should create.

    A "IndexCards Stack: ..." header line (from a previously copied-out
    stack) is dropped entirely; a "* "-prefixed bullet line has just its
    prefix stripped, so pasting an exported stack back in still produces
    one loose card per member — the stack grouping itself can't survive
    plain text, but the member cards' own text isn't polluted by the
    formatting used to display it in another app.

    denormalize_text runs last, after truncation — the inverse of
    plain_text_for_payload's normalize_text, expanding a single \\n back
    into whatever block-separator convention Card.text actually needs
    (see main_window._logical_text_to_card_text). Defaults to identity
    so this module stays Qt-free and independently testable; the real
    caller injects the markdown-aware expander.
    """
    results = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(STACK_HEADER_PREFIX):
            continue
        if line.startswith(STACK_BULLET_PREFIX):
            line = line[len(STACK_BULLET_PREFIX) :].strip()
            if not line:
                continue
        results.append(denormalize_text(_unescape_newlines(line)[:MAX_TEXT_LENGTH]))
    return results
