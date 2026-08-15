# Class diagram

The class diagram is the central canvas of BlueP. It shows every class in the
project as a box, with sections for fields and methods, and draws dependency
arrows between related classes.

## Creating classes

| Action | How |
|---|---|
| New class | Right-click diagram → **New Class**, or **Class → New** |
| Open editor | Double-click the class box, or right-click → **Open Editor** |
| Rename | Right-click → **Rename Class** (updates file, class def, and tab) |
| Delete | Right-click → **Delete Class** (asks for confirmation) |
| Instantiate | Right-click → **Instantiate** |

## Class kinds

Each kind gets a distinct visual style:

| Kind | Border style |
|---|---|
| Concrete | Solid |
| Abstract | Dashed (yellow) |
| Interface | Dashed (green) |
| Dataclass | Solid (orange) |
| Error | Dashed (red) — compilation failed |

## Dragging

Click and drag a class box to reposition it. Positions are saved to
`.bluep/diagram.json` and restored on the next project open.

## Right-click context menu

The context menu adapts to the target:

- **Diagram background**: New Class, Paste, Select All
- **Class box**: Open Editor, Instantiate, Rename, Delete, Compile
- **Object tile**: Inspect, Call Method, Remove from Bench
