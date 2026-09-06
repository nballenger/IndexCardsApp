from __future__ import annotations

from indexcards.models.document import Document


def repair_document(document: Document) -> list[str]:
    """Fixes up dangling references left by a hand-authored (e.g. agent-
    generated) file so the app never crashes rendering it, returning a
    human-readable message per repair made (empty list = nothing to fix,
    the overwhelmingly common case). Called once, right after a successful
    from_dict(), by file_io.load_document() -- never during live editing,
    where Document.add_link()'s own raise-on-bad-reference stays correct
    (a single interactive command failing loudly is right; a whole file
    failing to open over one bad reference is not).
    """
    messages: list[str] = []

    if document.theme.slots:
        default_slot_id = document.theme.slots[0].id
        valid_slot_ids = {slot.id for slot in document.theme.slots}
        for card in document.cards.values():
            if card.color_slot not in valid_slot_ids:
                messages.append(
                    f"Card {card.id!r} referenced unknown color_slot "
                    f"{card.color_slot!r}; reset to {default_slot_id!r}."
                )
                card.color_slot = default_slot_id

    for link_id in list(document.links.keys()):
        link = document.links[link_id]
        if link.source not in document.cards or link.target not in document.cards:
            messages.append(
                f"Link {link.id!r} referenced a nonexistent card "
                f"(source={link.source!r}, target={link.target!r}); removed."
            )
            del document.links[link_id]

    listed_in_stack: dict[str, str] = {}
    for stack in document.stacks.values():
        kept_ids = []
        for card_id in stack.card_ids:
            if card_id in document.cards:
                kept_ids.append(card_id)
                listed_in_stack[card_id] = stack.id
            else:
                messages.append(
                    f"Stack {stack.id!r} listed nonexistent card {card_id!r}; "
                    f"removed from pile."
                )
        stack.card_ids = kept_ids

    for card in document.cards.values():
        true_stack_id = listed_in_stack.get(card.id)
        if card.stack_id == true_stack_id:
            continue
        if card.stack_id is not None and true_stack_id is None:
            messages.append(
                f"Card {card.id!r} claimed stack_id {card.stack_id!r} but no "
                f"stack lists it; cleared."
            )
        elif card.stack_id is None and true_stack_id is not None:
            messages.append(
                f"Card {card.id!r} is listed in stack {true_stack_id!r} but had "
                f"no stack_id; set to match."
            )
        else:
            messages.append(
                f"Card {card.id!r} claimed stack_id {card.stack_id!r} but is "
                f"listed in stack {true_stack_id!r}; corrected to match the "
                f"stack's own membership."
            )
        card.stack_id = true_stack_id

    return messages
