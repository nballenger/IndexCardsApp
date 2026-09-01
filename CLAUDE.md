# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A desktop app (PySide6/Qt) that ports the "index cards on the kitchen table" workflow to a screen: freeform cards on a canvas, arranged, linked, colored, and grouped into stacks. See `README.md` for the full pitch, but the durable constraints worth internalizing before adding anything are:

1. **The card metaphor is not to be broken** — there is a hard limit on how much text fits on a card face (see `utils/text_limit.py`); don't add ways around it.
2. **Visual styling stays minimal and opinionated** — this is not meant to become a general theming/presentation tool.
3. **Features without a physical analog get scrutinized hard.** Tags were added, then mostly removed in favor of color labels (see `feature_flags.py` below) precisely because they didn't earn their keep. Default to skepticism of anything that doesn't have a "real index card" equivalent.
4. **It's not a webapp** — no backing service, no network dependency.
5. **It doesn't need AI features built in.**

If a request seems to cut against one of these, it's worth surfacing that tension rather than just implementing it.

## Commands

Dependency management and running everything goes through `uv`.

```bash
uv run indexcards              # launch the app
uv run pytest                  # run the full test suite
uv run pytest tests/test_models.py                    # single test file
uv run pytest tests/test_models.py -k test_add_card    # single test
uv run ruff check               # lint (see [tool.ruff] in pyproject.toml for the rule set)
uv run ruff check --fix         # lint, autofixing what's safe to fix
```

Tests use `pytest-qt` and need a Qt platform plugin to construct real widgets. On a headless/minimal Linux box (no X server, missing `libEGL`), set `QT_QPA_PLATFORM=offscreen` and make sure Qt's runtime libs (e.g. `libegl1`) are actually installed — `offscreen` alone doesn't help if the shared libraries themselves are missing. This has bitten sessions before (see `fad7280`, where a run's lint/test pass got silently skipped) — don't assume a clean run without actually seeing it execute.

## Architecture

**Document is the single source of truth**, and the only path for mutating app state. It's a `QObject` (`models/document.py`) owning `cards`, `links`, `stacks`, and the active `theme` as plain dicts. Every mutator method (`set_card_text`, `add_card`, `set_stack_card_order`, ...) does three things in order: mutate, mark dirty, emit a Qt signal (`cardChanged`, `stackAdded`, `themeChanged`, ...). Nothing should ever reach into `document.cards[id]` and mutate a `Card` directly — going around a mutator means the signal never fires and a view silently goes stale.

**Undo/redo wraps Document, it doesn't replace it.** Every user-facing edit is a `QUndoCommand` in `commands/` (`card_commands.py`, `stack_commands.py`, `theme_commands.py`, ...) whose `redo()`/`undo()` call Document mutators. Multi-step user actions (e.g. deleting a stack and its member cards, resolving several orphaned colors at once) are pushed as one `QUndoStack.beginMacro()/endMacro()` group so they undo atomically — see `MainWindow._on_delete_stack` and `_open_orphan_resolution` for the pattern. `QUndoStack` doesn't support nested macros, so a caller that needs to combine an already-macro'd helper (like `push_delete_stack_and_cards`) with more pushes of its own has to inline the helper's pushes instead of calling it.

**Two views mirror one Document, kept in sync via signals, never by polling each other.** `CanvasScene` (a `QGraphicsScene` in `canvas/`) and `CardTableModel`/`ListViewWidget` (a Qt item model in `list_view/`) both listen to the same Document's signals and update their own items/rows independently. `MainWindow` is the mediator for the one thing that needs explicit two-way sync — selection — using a `_syncing_selection` re-entrancy guard to stop the ping-pong. When adding a new piece of state to Card/Stack/Document, both views generally need their own signal handler; grep for an existing signal like `cardChanged` to find every place that already listens.

**Windows share state through `WindowManager`** (`window_manager.py`): one `MainWindow` per open file, but a single `QUndoGroup`, `AppSettings`, and `ThemeLibrary` shared across all of them, so undo targets whichever window is focused and preferences/custom themes are consistent everywhere. `MainWindow` also works standalone (constructed with `window_manager=None`, falling back to its own in-memory `QUndoGroup`/`AppSettings`/`ThemeLibrary`) — this is what most tests construct directly, so don't assume a `WindowManager` is always present.

**Persistence is a three-stage pipeline**, deliberately kept separate: `serializer.py` (`Document` ⇄ plain dict), `migrations.py` (upgrades an old on-disk dict, one schema version at a time, to `CURRENT_SCHEMA_VERSION`), `file_io.py` (dict ⇄ `.idxcards` JSON file on disk, calling `migrate()` before `from_dict()` on load). Any change to what gets saved needs a new schema version and a migration function added to `_MIGRATIONS`, following the existing steps as a template — each one is a pure `dict -> dict` transform, and they intentionally preserve data losslessly rather than dropping anything unrecognized (e.g. `_migrate_v4_to_v5` turns an unrecognized card color into its own orphaned theme slot rather than discarding it).

**Colors are theme slots, not literal hex values on a card.** A `Card.color_slot` references a `Slot` in the document's active `Theme` (`models/theme.py`); the same slot id can resolve to different hex values under different themes. Editing a theme or switching to a different one can leave slots "orphaned" (a slot a card still uses that the new/edited theme no longer defines) — `Document.plan_theme_edit`/`plan_theme_switch` compute what should happen without mutating anything, returning newly-orphaned slot ids for `MainWindow` to route through `OrphanResolutionDialog`. Orphan resolution itself goes through the same Document-mutator-plus-signal and undo-command pattern as everything else. `ThemeLibrary` (custom, user-created themes) is persisted separately from any one document's file — see `persistence/theme_library_io.py`.

**Auto-arrange lives in `arrange/`**, separate from the commands that apply its output — the arrange functions are pure (`cards/stacks in -> new positions out`), and `MainWindow` wraps the result in an `AutoArrangeCommand`/`GatherStacksCommand` push. Obstacle-awareness (arranging cards without overlapping stacks) is a parameter threaded through, not a separate code path.

**`feature_flags.py` hides finished-but-disabled features** rather than deleting their code (`TAGS_ENABLED` is the current example — tags were pulled from the UI per constraint #3 above, but the underlying model/persistence support is intact). If you're asked to fully remove such a feature, confirm that's actually the intent rather than just flipping the flag back on.

## Conventions

- Commit messages follow `M<n>: <description>` for milestone work (`git log` for the numbering so far); plain `Fix: ...` for bugfixes outside a milestone.
- `from __future__ import annotations` at the top of every module; modern `X | None` union syntax throughout (ruff's `UP` rule enforces this).
- Comments in this codebase are almost all "why", not "what" — explaining a non-obvious ordering constraint, a Qt quirk being worked around, or why a simpler approach doesn't work. Match that bar rather than narrating what the code does.
- `tests/conftest.py` auto-uses the `qapp` fixture and monkeypatches `QMessageBox.question` to always return Discard, so a dirty window left open at test teardown doesn't pop a real blocking modal. A test that cares about a specific dialog response sets its own monkeypatch after that default.
