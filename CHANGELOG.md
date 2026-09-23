# Changelog

All notable changes to IndexCards are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/) (pre-1.0, so minor versions may
change behavior or remove features).

## [Unreleased]

### Added

- **Regions (early version).** A labeled, resizable zone drawn behind cards
  and stacks, marking a cluster as a related set -- the closest analog is a
  sheet of paper under a pile of physical cards. Create one with **Edit >
  Region from Selection** or right-click empty canvas > **New Region Here**;
  drag its label bar to move it (and whatever's inside), drag its border to
  resize it, or right-click it to relabel or delete it. Membership is
  derived from position (a card belongs if its center is inside), so
  regions may nest and overlap.

- **Auto-arrange now respects regions.** Tile, Scatter, both Columns modes,
  Untangle Links, Gather Stacks, Explode Stack, and Tidy/Sweep to Edges all
  leave a card or stack inside a region exactly where it is, the same as a
  pinned card, and treat a region's rectangle as reserved space a fresh
  layout won't land on. Gather Stacks and Tidy/Sweep to Edges only skip
  moving what's already inside a region -- they don't route a freshly
  placed card or stack around one that happens to be in the way.

- **Dropping a card or stack on a region's border now snaps it fully in or
  out**, whichever side its center landed on, instead of letting it sit
  half in and half out. A multi-card drag resolves as one rigid group. If
  no nearby position satisfies every region at once, the drop is reverted
  instead of leaving something stuck straddling a border. Creating a card
  -- by double-clicking or with File > New Card -- gets the same
  treatment, so a brand new card can't straddle a region either.

- **Opening a file now repairs region problems the same way a live drag
  already prevents them** -- an overlap or nested gap too thin to hold a
  card gets grown, and a card or stack straddling a border gets moved
  fully to one side, each reported in the usual load-warnings. Only
  matters for a file that didn't come from a drag in this app -- one
  that's hand-edited, agent-written, or from a version with its own bug.

- **A region's label now sits on a real title bar** -- a solid strip across
  the top, colored like the region's own border, with text in whichever
  neutral reads clearly against it -- instead of plain text over the same
  faint tint as the rest of the region.

- **Cards and stacks now keep a small buffer from a region's rounded
  corners and stay below its title bar**, rather than snapping flush
  against the raw edge (which could look like it overlapped the rounded
  corner) or resting on top of the label. Applies everywhere a card/stack
  is placed against a region -- dragging, creating, and the load-time
  repair above.

- **A region now grows itself, automatically, rather than ever letting some
  part of the board become too small to hold a card** -- the space left
  around a region nested inside another, or the sliver where two regions
  overlap, always keeps room for at least one card. When dragging a region
  causes it to overlap another, it tries moving clear of the other region
  first, and only makes the region it landed on grow if there's nowhere
  clear nearby -- that specific choice is still provisional and may change
  based on how it feels in real use.

- `indexcards --format-guide` and `indexcards --schema` print the file format
  guide and its JSON Schema without opening the app, so an agent can read the
  format from whichever install it has (including the macOS app bundle).
- A small Claude Code skill in `skills/indexcards/` that points an agent at
  those commands and at `indexcards --validate`. Copy it into
  `~/.claude/skills/` to use it.

### Changed

- The format guide embedded in every saved file now tells an agent how to
  check its own output with `indexcards --validate`, and how big a card is when
  laying cards out.
- The JSON Schema moved to `src/indexcards/persistence/idxcards.schema.json` so
  it ships with the package and the app bundle.

## [0.2.0] - 2026-09-19

### Added

- **References on the back of a card.** A card can carry up to two references,
  each a text label, a URL, or both -- the source of an idea, like the citation
  you might jot on the back of a physical index card.
- **Card Info dialog**, opened with right-click > Get Info or Edit > Card Info
  (`Cmd+Shift+I`). It shows when the card was created and last modified, and
  lets you add or edit its references.
  - Text with a URL shows as a link, text alone as plain text, and a URL alone
    as a link labeled with its domain. Links open in the default browser.
  - A URL without `https://` (such as `mozilla.org`) still opens, and a value
    that isn't plausibly a URL is shown as plain text instead of a broken link.
- Cards with references show a folded bottom-right corner, and hovering one
  lists what's on its back.

### Changed

- Documents are saved as schema version 10 to store references. Older files
  open and upgrade automatically; a file saved by this version cannot be opened
  by v0.1.x.

### Removed

- **The List view.** The canvas is now the only view, so the List tab and the
  View > Canvas / List switching (`Cmd+1` / `Cmd+2`) are gone.

### Fixed

- The Pin Card shortcut (`Cmd+Shift+P`) could stay disabled after selecting a
  card until the Edit menu had been opened once. It now tracks the selection.

## [0.1.1] - 2026-09-15

### Changed

- Depend on `pyside6-essentials` instead of the full `pyside6` package, cutting
  the install footprint by about two thirds (a development environment drops
  from roughly 1.2 GB to 380 MB).

## [0.1.0] - 2026-09-12

First public version.

### Added

- Freeform cards on a canvas, groupable into stacks, with a canvas list view
  kept in sync with the board.
- Links between cards, with adjustable line endings, colors, and weight.
- Auto-arrange tools: tile, scatter, align, distribute, columns, gather stacks,
  and untangle links.
- Color themes: four built-in palettes (including a high-contrast accessible
  one) and custom themes you can build and edit.
- Adaptive card text that shrinks to fit the card face.
- Search, undo/redo for every action, and cut/copy/paste for cards and stacks.
- Plain, documented JSON `.idxcards` file format, readable and editable by hand
  or by an external AI agent.
- A macOS app build and generated app icon.

[Unreleased]: https://github.com/nballenger/IndexCardsApp/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/nballenger/IndexCardsApp/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/nballenger/IndexCardsApp/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/nballenger/IndexCardsApp/releases/tag/v0.1.0
