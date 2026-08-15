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

| Trigger | Behaviour |
|---|---|
| Type a word | Completions appear automatically after each keystroke |
| `Ctrl+Space` | Force completion at the cursor |
| `Up` / `Down` | Navigate the completion list |
| `Tab` / `Enter` | Apply the selected completion |
| `Escape` | Dismiss the completion popover |

Completion sources:

- Python keywords (`keyword.kwlist`)
- Python builtins (`dir(builtins)`)
- Words from the current buffer (case-insensitive prefix match)

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
| `Tab` | Insert configured spaces |
| `Enter` | Newline with auto-indent |
| `Escape` | Dismiss autocomplete popover |
