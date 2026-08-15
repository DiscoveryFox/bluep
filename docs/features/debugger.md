# Debugger

BlueP includes a step-by-step debugger with breakpoint management, variable
inspection, and a call-stack view.

## Setting breakpoints

Click the gutter to the left of a line in the code editor, or press `Ctrl+B`
at the cursor line. A breakpoint marker appears in the gutter. Click again (or
`Ctrl+B`) to remove it.

## Running the debugger

1. Set at least one breakpoint.
2. Start a method call from the object bench (right-click → **Call Method**).
3. Execution pauses at the first breakpoint hit.

## Stepping

| Action | Description |
|---|---|
| Step Over | Execute the current line, pause at the next line in the same scope |
| Step Into | Enter the function/method called on the current line |
| Step Out | Run until the current function returns |
| Continue | Run until the next breakpoint or end |

## Variable inspection

The debug panel shows all local and instance variables at the current
execution point. Values update as you step.

## Call stack

The call stack view shows the chain of active function calls. Click a frame to
switch to that scope in the variable inspector.
