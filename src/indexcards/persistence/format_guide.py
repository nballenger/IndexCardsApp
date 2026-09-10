from __future__ import annotations

# Embedded verbatim into every saved .idxcards file (see serializer.to_dict's
# "_format_guide" key) so an LLM-based agent with zero prior knowledge of this
# app can open a file directly and understand it correctly -- constraint #5 in
# CLAUDE.md keeps AI features out of the app itself, but a file format that's
# legible to an external agent driving the app via files is a different thing
# entirely and is explicitly fine. Purely a write-time stamp, never read back
# into any Document attribute (same pattern as serializer.APP_VERSION) -- keep
# this in sync with the schema by eye whenever a Document/Card/Link field with
# real semantic meaning is added or changed, same review discipline as a
# migration, just without the version-bump machinery since nothing here is
# round-tripped through app state.
FORMAT_GUIDE = """\
This is an IndexCards document (.idxcards): a board of short text notes ("cards")
arranged freely on a 2D canvas, styled with theme colors, optionally grouped into
ordered piles ("stacks"), and optionally connected by labeled lines ("links"). It
models physical index cards on a table, not a document or outline — order and
hierarchy are NOT implied by list position in this JSON; only explicit fields
(position, stack_id, card_ids order, link source/target) carry meaning.

Entities:
- cards: the notes themselves. Each has free-text `text`, an (x, y) canvas
  position, a `color_slot` (see Colors below), and an optional `stack_id`
  pointing at the stack it currently belongs to (null if free on the canvas).
  `tags` may be present but is a legacy/hidden field in the current app UI —
  treat it as inert unless the user says otherwise.
- stacks: an ordered pile of cards. `card_ids` is the pile's front-to-back (or
  reading) order — this is meaningful and intentional, not incidental. A
  stack has its own (x, y) position on the canvas; member cards' own x/y are
  not used while stacked.
- links: a labeled line between exactly two cards (`source` -> `target`, both
  card ids). `label` is free text describing the relationship in the user's
  own words — there is no fixed vocabulary of relationship types.
  `line_ending` (none / to_target / to_source / both) is rendered by the app
  as pure arrowhead style with no enforced meaning, but by convention in this
  document it also signals the author's view of the relationship: "none" =
  an association exists with no implied direction or causality; a
  single-direction arrow = a directional relationship (e.g. causal,
  sequential, dependent) running the way the arrow points; "both" = a
  bidirectional or mutually-reinforcing relationship. Treat this as the
  author's intent, not an app-enforced rule. Taken together, the `links`
  array is a complete directed edge list over card ids — the whole graph.
  Connected components, clusters, hubs, or cycles are never marked
  explicitly anywhere else in the data; if they matter, derive them by
  traversing this edge list yourself.
- theme: the active color palette for this document, as a list of named
  "slots" (id, label, hex). A card's `color_slot` is a REFERENCE to one of
  these slots, not a color itself — to know what color a card actually is,
  look up its `color_slot` id in `theme.slots`. The same slot id can mean a
  different hex value in a different theme, and the slot's `label` is the
  user's own name for what that color means in this document (e.g. "Needs
  research", "Done") — there is no fixed meaning across documents.

Text encoding:
- `card.text` is stored as Markdown, not plain text. A block break (the user
  pressing Enter while editing) is a BLANK LINE ("\\n\\n"), not a single "\\n" —
  a lone "\\n" is just a soft wrap within one paragraph. When reading or
  rewriting card text, treat blank-line-separated chunks as the card's real
  line/paragraph structure.
- Cards are short by design (the physical-index-card metaphor is load-bearing
  in this app): text is capped at 560 characters. Don't propose or generate
  card text longer than that. The app also shrinks a card's font/line-spacing/
  padding to fit whatever text is there, so shorter text within the cap still
  renders larger and more legibly -- shorter is still better where it works.

Spatial and ordering semantics:
- (x, y) positions on the canvas reflect intentional arrangement (proximity,
  clustering, grouping) — preserve or reason about them as meaningful
  authoring choices, not layout noise, unless asked to rearrange.
- A stack's `card_ids` order is meaningful (it's the pile order); the
  top-level `cards` and `stacks` array order in this JSON is not — it's
  incidental to how the file was written and carries no semantics.
- `pinned`: the app's auto-arrange tools skip a pinned card when
  repositioning things, and creating a link auto-pins both its endpoint
  cards by default (removing a link never unpins). Pinned is a signal that
  the human placed this card deliberately and it should stay put.
  The flip side is a hedge, not a green light: an *unpinned* card's
  position can still be real authoring signal (see the point above) — being
  unpinned doesn't mean the position is noise, only that it isn't protected
  from being rewritten wholesale by an auto-arrange action (the human's own,
  or one you run yourself). Treat unpinned-card position as meaningful but
  brittle: worth reasoning about as it currently stands, but don't assume it
  will still be there after any arrangement operation.

IDs:
- `id` fields (on cards, links, stacks, and theme slots) are opaque unique
  strings — nothing reads meaning out of their shape. The app generates its
  own as a short prefix plus a random hex suffix (`c_`/`l_`/`s_`), but any
  unique string works fine when authoring or editing a file by hand; you do
  not need to imitate that format.

What can be omitted:
- Only `id` is truly required on a card, link, or stack — everything else
  has a sensible default if left out: a card defaults to empty text, (0, 0)
  position, the app's own default color slot, no tags, unpinned, and no
  stack; a link defaults to an empty label and "none" line ending; a stack
  defaults to an empty pile and label. A link still needs a real `source`
  and `target`, though — those are the only fields besides `id` that a link
  can't function without.

Minimal document template (a complete, valid, empty-ish starting point —
copy this and add your own cards/links/stacks; the theme's single slot
matches the app's own built-in default color, so cards can omit
`color_slot` entirely and still resolve correctly):

    {
      "schema_version": 9,
      "app_version": "0.1.0",
      "file": {"name": "New Document"},
      "theme": {
        "id": "theme_custom", "name": "Simple", "origin": "custom",
        "background_color": "#3d6b4f", "link_color": "#808080",
        "link_color_mode": "theme", "link_weight": 2,
        "slots": [
          {"id": "slot_white", "label": "Default", "hex": "#ffffff"}
        ]
      },
      "cards": [
        {"id": "c_1", "text": "Hello", "position": {"x": 0, "y": 0}}
      ],
      "links": [],
      "stacks": []
    }

This file is schema_version-stamped and forward-migrated by the app itself;
this guide describes that schema version. Fields not mentioned here are
either bookkeeping (ids, timestamps) or view state (zoom, scroll position)
with no content meaning.
"""
