---
name: indexcards
description: Create, edit, or check IndexCards board files (.idxcards) -- plain-JSON documents of index cards with positions, colors, stacks, and links. Use when asked to build or modify an IndexCards board, turn ideas into cards, or validate a .idxcards file.
---

# IndexCards boards

An `.idxcards` file is plain JSON, and the app documents its own format. Don't
guess at fields; read the docs from the app first.

## Running the app's commands

Use whichever of these works on this machine, then add the flag:

- `indexcards` if it is on the PATH
- `uv run --directory <path to the IndexCards checkout> indexcards`
- `/Applications/IndexCards.app/Contents/MacOS/IndexCards` (macOS app bundle;
  the location may differ)

If none of these works, ask the user where IndexCards is installed. Don't
search the filesystem for it.

## Steps

1. `indexcards --format-guide` prints the format guide: what each entity means,
   the text limit, spatial and color conventions, and a minimal valid document
   to start from. Read it before writing anything.
2. `indexcards --schema` prints the JSON Schema, if you need exact field types.
3. Write the `.idxcards` file where the user asked.
4. `indexcards --validate <file>` checks it without opening the app. It exits
   non-zero on any problem, including ones the app would silently repair, so
   keep fixing the file until it prints `OK`.

Only write the board file. Don't modify the IndexCards install or source, and
don't open the GUI.
