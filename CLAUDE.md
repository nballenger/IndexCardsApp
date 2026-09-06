# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A desktop app (PySide6/Qt) that ports the "index cards on the kitchen table" workflow to a screen: freeform cards on a canvas, arranged, linked, colored, and grouped into stacks. See `README.md` for the full pitch, but the durable constraints worth internalizing before adding anything are:

1. **The card metaphor is not to be broken** — there is a hard limit on how much text fits on a card face (see `utils/text_limit.py`); don't add ways around it.
2. **Visual styling stays minimal and opinionated** — this is not meant to become a general theming/presentation tool.
3. **Features without a physical analog get scrutinized hard.** Tags were added, then mostly removed in favor of color labels (see `feature_flags.py` below) precisely because they didn't earn their keep. Default to skepticism of anything that doesn't have a "real index card" equivalent.
4. **Documents are an open, self-describing format.** `.idxcards` files are plain JSON, not binary or proprietary — and, per constraint 6 below, deliberately built to be a self-contained unit of meaning an external agent can read and correctly write without opening the app (see the embedded `_format_guide` field, `schema/idxcards.schema.json`, and `persistence/validation.py`'s repair-on-load pass).
5. **It's not a webapp** — no backing service, no network dependency.
6. **It doesn't need AI features built into the app itself** — bringing your own external AI agent to drive it via the file format (constraint 4) is explicitly fine and intended.

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

**On a real dev machine (e.g. local macOS) there is typically no offscreen platform available at all — tests and scripts run against a real display.** This cuts the other way from the headless case above: a code path that pops a real, unmocked `QMenu`/`QDialog`/`QMessageBox` (including one newly added *inside* an already-tested handler) doesn't silently no-op — it blocks waiting for real input, hanging the test run or a verification script outright, sometimes only surfacing minutes later as a timeout. Always mock the specific dialog call in tests (see `conftest.py`'s `QMessageBox.question` default below for the pattern), and never leave a dirtied `MainWindow` open at the end of a one-off verification script — closing it can trigger a real "save changes?" prompt with nothing there to answer it.

## Architecture

**Document is the single source of truth**, and the only path for mutating app state. It's a `QObject` (`models/document.py`) owning `cards`, `links`, `stacks`, and the active `theme` as plain dicts. Every mutator method (`set_card_text`, `add_card`, `set_stack_card_order`, ...) does three things in order: mutate, mark dirty, emit a Qt signal (`cardChanged`, `stackAdded`, `themeChanged`, ...). Nothing should ever reach into `document.cards[id]` and mutate a `Card` directly — going around a mutator means the signal never fires and a view silently goes stale.

**Undo/redo wraps Document, it doesn't replace it.** Every user-facing edit is a `QUndoCommand` in `commands/` (`card_commands.py`, `stack_commands.py`, `theme_commands.py`, ...) whose `redo()`/`undo()` call Document mutators. Multi-step user actions (e.g. deleting a stack and its member cards, resolving several orphaned colors at once) are pushed as one `QUndoStack.beginMacro()/endMacro()` group so they undo atomically — see `MainWindow._on_delete_stack` and `_open_orphan_resolution` for the pattern. `QUndoStack` doesn't support nested macros, so a caller that needs to combine an already-macro'd helper (like `push_delete_stack_and_cards`) with more pushes of its own has to inline the helper's pushes instead of calling it.

**Two views mirror one Document, kept in sync via signals, never by polling each other.** `CanvasScene` (a `QGraphicsScene` in `canvas/`) and `CardTableModel`/`ListViewWidget` (a Qt item model in `list_view/`) both listen to the same Document's signals and update their own items/rows independently. `MainWindow` is the mediator for the one thing that needs explicit two-way sync — selection — using a `_syncing_selection` re-entrancy guard to stop the ping-pong. When adding a new piece of state to Card/Stack/Document, both views generally need their own signal handler; grep for an existing signal like `cardChanged` to find every place that already listens.

**Windows share state through `WindowManager`** (`window_manager.py`): one `MainWindow` per open file, but a single `QUndoGroup`, `AppSettings`, and `ThemeLibrary` shared across all of them, so undo targets whichever window is focused and preferences/custom themes are consistent everywhere. `MainWindow` also works standalone (constructed with `window_manager=None`, falling back to its own in-memory `QUndoGroup`/`AppSettings`/`ThemeLibrary`) — this is what most tests construct directly, so don't assume a `WindowManager` is always present.

**Persistence is a three-stage pipeline**, deliberately kept separate: `serializer.py` (`Document` ⇄ plain dict), `migrations.py` (upgrades an old on-disk dict, one schema version at a time, to `CURRENT_SCHEMA_VERSION`), `file_io.py` (dict ⇄ `.idxcards` JSON file on disk, calling `migrate()` before `from_dict()` on load). Any change to what gets saved needs a new schema version and a migration function added to `_MIGRATIONS`, following the existing steps as a template — each one is a pure `dict -> dict` transform, and they intentionally preserve data losslessly rather than dropping anything unrecognized (e.g. `_migrate_v4_to_v5` turns an unrecognized card color into its own orphaned theme slot rather than discarding it).

**Colors are theme slots, not literal hex values on a card.** A `Card.color_slot` references a `Slot` in the document's active `Theme` (`models/theme.py`); the same slot id can resolve to different hex values under different themes. Editing a theme or switching to a different one can leave slots "orphaned" (a slot a card still uses that the new/edited theme no longer defines) — `Document.plan_theme_edit`/`plan_theme_switch` compute what should happen without mutating anything, returning newly-orphaned slot ids for `MainWindow` to route through `OrphanResolutionDialog`. Orphan resolution itself goes through the same Document-mutator-plus-signal and undo-command pattern as everything else. `ThemeLibrary` (custom, user-created themes) is persisted separately from any one document's file — see `persistence/theme_library_io.py`. Switching between two themes with no shared slot ids (e.g. two different presets) still avoids orphaning everything: `plan_theme_switch` falls back to matching the Nth active slot in the old theme to the Nth active slot in the new one when an exact id match fails, returned as a `color_slot_remap` applied atomically with the theme swap.

**`Card.text` is stored as markdown, not plain text** (`canvas/card_item.py`'s `_CardTextItem` commits via `document().toMarkdown()` and reloads via `setMarkdown()` — this is also how the in-card Bold/Italic shortcuts round-trip). A hard line break (plain Enter while editing — there's no Shift+Enter distinction) becomes a **blank-line block separator** (`"Alpha\n\nBravo"`), not a single `\n`. Any code that treats `card.text` as plain text — counting characters, splitting/joining lines, exporting it outside the app — has to round-trip through a real `QTextDocument` first to normalize, or it will double newlines on the way out and collapse a multi-line card onto one line on the way back in (a bare single `\n` fed to `setMarkdown()` is just a *soft* break within one paragraph, not a new block).

**Auto-arrange lives in `arrange/`**, separate from the commands that apply its output — the arrange functions are pure (`cards/stacks in -> new positions out`), and `MainWindow` wraps the result in an `AutoArrangeCommand`/`GatherStacksCommand` push. Obstacle-awareness (arranging cards without overlapping stacks) is a parameter threaded through, not a separate code path.

**`feature_flags.py` hides finished-but-disabled features** rather than deleting their code (`TAGS_ENABLED` is the current example — tags were pulled from the UI per constraint #3 above, but the underlying model/persistence support is intact). If you're asked to fully remove such a feature, confirm that's actually the intent rather than just flipping the flag back on.

## Known gotchas

- **A `QAction`'s keyboard shortcut only fires while the action is actually enabled at that instant.** Refreshing enabled state lazily — e.g. only on the containing menu's `aboutToShow` — leaves the shortcut silently inert between refreshes, since the menu-click path always re-checks right before firing but the shortcut path doesn't. This also bites at construction time: a one-time enabled-state check run before the state it depends on (e.g. `self.document`) is actually established will leave a freshly created window's shortcut stuck disabled until some unrelated signal happens to fire. Wire the refresh to every real signal that can change the answer, and call it once more after construction finishes, not just once during it.
- **Never delete/replace a `QGraphicsItem` (or push a command that does) from inside that same item's own event handler, or while any item's mouse grab is active.** Qt doesn't tolerate an item being torn down while it's still on the event-dispatch call stack. If a `redo()`/`undo()` triggered from inside a press/release/drag handler could rebuild the scene, defer the push with `QTimer.singleShot(0, ...)` so the current dispatch fully unwinds first, and capture whatever the deferred callback needs as locals at schedule time (not via `self.` lookups later) — the widget can legitimately be gone by the time the timer fires. See `canvas/stack_overlay.py` for the pattern (drag-to-reorder/drag-to-eject inside a Stack's contents overlay).
- **An unhandled exception raised inside a Qt-invoked override (`paint()`, `viewportEvent`, etc.) segfaults the interpreter — it does not raise a normal Python traceback.** If something inside a paint path looks like it silently swallowed an error rather than crashing loudly, that's the likely cause; keep such overrides defensive rather than assuming an exception there will surface normally.
- **Before shipping a "fix" for a randomized or purely-visual layout algorithm (Scatter, Tidy/Sweep to Edges, anything under `arrange/`), verify the actual emergent behavior empirically — across many seeds/inputs — rather than trusting a plausible-sounding mechanism.** This codebase has shipped a "fix" for an observed bias that was actually just ordinary run-to-run variance, and separately shipped a spiral-tiling algorithm that passed every generic unit test (`no overlap`, `covers every card`) on two different visibly-broken versions before the actual layout was checked by eye. Generic invariant tests aren't a substitute for looking at the output.

## Conventions

- Commit messages followed `M<n>: <description>` for milestone work through M57 (`git log` for the numbering); since then the project moved to plain, imperative, descriptive titles instead (e.g. `Add Cut/Copy/Paste for cards and Stacks`, `Restructure Theme menu; make auto-arrange and Gather Stacks obstacle-aware`) — `Fix: ...` still shows up for pure bugfixes but isn't required. Check recent `git log` output rather than assuming the `M<n>:` scheme is still current.
- `from __future__ import annotations` at the top of every module; modern `X | None` union syntax throughout (ruff's `UP` rule enforces this).
- Comments in this codebase are almost all "why", not "what" — explaining a non-obvious ordering constraint, a Qt quirk being worked around, or why a simpler approach doesn't work. Match that bar rather than narrating what the code does.
- `tests/conftest.py` auto-uses the `qapp` fixture and monkeypatches `QMessageBox.question` to always return Discard, so a dirty window left open at test teardown doesn't pop a real blocking modal. A test that cares about a specific dialog response sets its own monkeypatch after that default.
