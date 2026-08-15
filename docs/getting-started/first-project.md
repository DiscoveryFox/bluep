# Your first project

This walkthrough builds a simple `Counter` class, instantiates it, and
exercises it on the object bench.

## 1. Create the project

`Project → New`, name it `counter-demo`, pick an empty directory.

## 2. Add the `Counter` class

Right-click the diagram → **New Class** → name: `Counter` → kind: Concrete.

Open the editor and paste:

```python
class Counter:
    def __init__(self, start: int = 0, step: int = 1):
        self.value = start
        self.step = step

    def increment(self) -> int:
        self.value += self.step
        return self.value

    def decrement(self) -> int:
        self.value -= self.step
        return self.value

    def reset(self) -> None:
        self.value = 0

    def __repr__(self) -> str:
        return f"Counter(value={self.value}, step={self.step})"
```

Press `Ctrl+S` to save and compile.

## 3. Instantiate

Right-click the `Counter` box → **Instantiate**. Use `5` as the constructor
argument (for `start`). The object `counter1` appears on the bench.

## 4. Call methods

Right-click `counter1` → **Call Method** → `increment`. The return value `6`
is shown. Call it a few more times.

## 5. Inspect

Right-click `counter1` → **Inspect**. The object inspector shows the current
fields: `value` and `step`.

## 6. Use the code pad

Switch to the **Code Pad** tab and type:

```python
counter1.value
```

Press Enter to see the current value.

!!! tip "Code pad state"
    The code pad has access to all objects on the bench by their variable
    names (`counter1`, `counter2`, etc.). Use it to inspect state or run
    quick computations without modifying the class.
