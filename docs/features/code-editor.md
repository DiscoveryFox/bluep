# Code editor

The BlueP code editor is a syntax-highlighted Python editor built on
GtkSourceView 5 (with a plain `Gtk.TextView` fallback when GtkSourceView is
unavailable).

## Tab key

The Tab key inserts `tab_width` spaces (default 4), not a tab character. This
is the most common source of editor discomfort in GTK editors — GTK's default
Tab width is 8 — so BlueP intercepts the Tab key explicitly and inserts the
configured number of spaces.

Change the width in **Edit → Preferences → Editor → Tab width**.

## Autocomplete

Completions appear as **inline ghost text** — a greyed-out preview of the top
match shown immediately after the cursor. No dropdown popover is displayed.

| Trigger | Behaviour |
|---|---|
| Type a word | Ghost text appears showing the best match suffix |
| `Ctrl+Space` | Force completion at the cursor |
| `Up` / `Down` | Cycle candidates; ghost text updates to the selected match |
| `Tab` or `Enter` | Accept the ghost text (configurable via *accept key*) |
| `Escape` | Dismiss the ghost text |

Completion sources:

- Python keywords (`keyword.kwlist`)
- Python builtins (`dir(builtins)`)
- Words from the current buffer (case-insensitive prefix match)
- Attribute completions after `.` on bench objects

An overlap guard hides ghost text when non-whitespace text follows the cursor
on the same line, preventing preview collisions with existing code.

Enable/disable in **Edit → Preferences → Editor → Enable autocomplete**.

## Bracket auto-closing

Typing an opening bracket `(`, `[`, or `{` inserts the matching close bracket
and places the cursor between them. Typing a quote `'` or `"` inserts the
matching quote; if the next character is already the same quote, the cursor
skips over it instead of doubling.

## Auto-indent

On Enter, the editor copies the current line's leading whitespace to the next
line. If the line ends with `:` (a block start), one extra indent level is
added.

## Breakpoints

Click the gutter to toggle a breakpoint, or press `Ctrl+B` at the cursor line.
Breakpoints are used by the [debugger](debugger.md).

## Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+S` | Save and compile |
| `Ctrl+B` | Toggle breakpoint at cursor |
| `Ctrl+Space` | Force autocomplete |
| `Ctrl+0/+/-` | Reset / zoom in / zoom out font size |
| `Tab` | Insert configured spaces or accept ghost text |
| `Enter` | Newline with auto-indent or accept ghost text |
| `Up` / `Down` | Cycle autocomplete candidates (when ghost text visible) |
| `Escape` | Dismiss ghost text |
