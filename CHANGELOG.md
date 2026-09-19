# Changelog

All notable changes to IndexCards are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/) (pre-1.0, so minor versions may
change behavior or remove features).

## [Unreleased]

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
