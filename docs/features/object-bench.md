# Object bench

The object bench sits at the bottom of the main window. It holds live Python
objects you have instantiated, so you can call methods and inspect state across
multiple interactions.

## Instantiating

Right-click a class box → **Instantiate**. If the class has a constructor
(`__init__`), BlueP shows a parameter dialog where you provide arguments. The
object appears on the bench with a generated name (`counter1`, `counter2`, …).

## Calling methods

Right-click a bench object → **Call Method**. BlueP shows a dialog listing all
public methods. Select one, provide arguments, and click **Call**. The return
value is displayed in the result field.

## Inspecting

Right-click a bench object → **Inspect**. The object inspector shows all
instance fields and their current values. Static/class fields are shown in a
separate section.

## Removing

Right-click a bench object → **Remove from Bench**. The object is removed from
the bench. Any remaining references in the code pad or other objects are not
affected.

## Recompile

When you recompile a project, the bench is cleared by default
(`BLUEP_CLEAR_BENCH_ON_RECOMPILE=true`) because existing objects reference the
old class definitions. Set this to `false` if you want objects to persist
across recompiles (their methods will still reference the old definitions until
Python garbage-collects them).
