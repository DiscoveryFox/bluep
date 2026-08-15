# Code pad

The code pad is a REPL-style scratch pad at the bottom of the main window. It
lets you evaluate Python expressions against the current project state without
modifying any class source files.

## What the code pad sees

The code pad has access to:

- All objects currently on the [object bench](object-bench.md), by their
  variable names (`counter1`, `counter2`, etc.)
- The standard Python builtins (`print`, `range`, `len`, …)
- Any imports present in the compiled project state

## Using the code pad

1. Click the **Code Pad** tab at the bottom of the window.
2. Type a Python expression.
3. Press `Enter` to evaluate.
4. The result appears inline below your input.

```python
counter1.value          # → 6
counter1.increment()    # → 7
type(counter1)          # → <class 'Counter'>
sum(o.value for o in [counter1, counter2])  # → 12
```

## When to use it

- Quick state checks without opening the inspector
- Ad-hoc computations combining multiple bench objects
- Testing a hypothesis before editing a class
