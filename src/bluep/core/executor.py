"""Python code execution engine for BlueP.

Handles compiling/executing Python classes and creating objects on the
object bench - mirroring BlueJ's compile + instantiate workflow.

The executor maintains a persistent namespace so objects on the bench
persist between operations, and uses Python's built-in exec() for code
evaluation (the Python equivalent of Java's classloader + reflection).
"""

from __future__ import annotations

import ast
import inspect
import io
import sys
import traceback
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from collections.abc import Iterator


@dataclass
class ExecutionResult:
    """Result of executing code."""
    success: bool
    output: str = ""
    error: str = ""
    value: Any | None = None
    traceback_str: str = ""

    @property
    def has_error(self) -> bool:
        return not self.success


@dataclass
class BenchObject:
    """An object placed on the object bench.

    Each bench object wraps a live Python instance, exactly like BlueJ's
    object bench holds live Java objects.
    """
    name: str
    instance: Any
    class_name: str
    methods: list[str] = field(default_factory=list)
    fields: list[tuple[str, str]] = field(default_factory=list)  # (name, value_str)

    def get_class_name(self) -> str:
        return self.instance.__class__.__name__

    def get_public_methods(self) -> list[str]:
        """Return public method names of the wrapped instance."""
        members = inspect.getmembers(self.instance, predicate=inspect.ismethod)
        return [name for name, _ in members if not name.startswith("_")]

    def get_static_methods(self) -> list[str]:
        """Return static/class method names from the class."""
        result = []
        cls = type(self.instance)
        for name, member in inspect.getmembers(cls):
            if not name.startswith("_"):
                obj = inspect.getattr_static(cls, name, None)
                if isinstance(obj, (staticmethod, classmethod)):
                    result.append(name)
        return result

    def get_fields(self) -> list[tuple[str, str]]:
        """Return (name, value) pairs for instance attributes."""
        result = []
        for name, value in vars(self.instance).items():
            result.append((name, repr(value)))
        return result

    def call_method(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        """Call a method on the wrapped instance."""
        method = getattr(self.instance, method_name)
        return method(*args, **kwargs)

    def get_field_value(self, field_name: str) -> Any:
        """Get a field value from the wrapped instance."""
        return getattr(self.instance, field_name)

    def set_field_value(self, field_name: str, value: Any) -> None:
        """Set a field value on the wrapped instance."""
        setattr(self.instance, field_name, value)

    def inspect(self) -> dict[str, Any]:
        """Full inspection of the object - like BlueJ's object inspector."""
        cls = type(self.instance)
        instance_fields = {}
        for name, value in vars(self.instance).items():
            instance_fields[name] = {
                "value": value,
                "type": type(value).__name__,
            }
        class_fields = {}
        for name in dir(cls):
            if not name.startswith("_"):
                attr = inspect.getattr_static(cls, name, None)
                if not callable(attr) and attr is not None:
                    class_fields[name] = {
                        "value": attr,
                        "type": type(attr).__name__,
                    }
        methods = {}
        for name, member in inspect.getmembers(self.instance, predicate=inspect.ismethod):
            if not name.startswith("_"):
                sig = inspect.signature(member)
                methods[name] = {
                    "params": [(p.name, str(p.annotation) if p.annotation != p.empty else None,
                                str(p.default) if p.default != p.empty else None) for p in sig.parameters.values()],
                    "return": str(sig.return_annotation) if sig.return_annotation != sig.empty else None,
                    "doc": inspect.getdoc(member),
                }
        return {
            "class_name": cls.__name__,
            "instance_fields": instance_fields,
            "class_fields": class_fields,
            "methods": methods,
        }


class CodeExecutor:
    """Executes Python code in a persistent namespace.

    This is the engine that powers:
    - Compiling (checking syntax + loading) classes
    - Instantiating objects on the object bench
    - Evaluating expressions in the code pad
    - Running the debugger
    """

    def __init__(self, project_path: Path | None = None) -> None:
        self.project_path = project_path
        self.namespace: dict[str, Any] = {
            "__name__": "__main__",
            "__builtins__": __builtins__,
        }
        self.bench: dict[str, BenchObject] = {}
        self._bench_counter: dict[str, int] = {}
        self._output_buffer = io.StringIO()
        self._old_stdout: Any = None
        self._capture_output = False
        if project_path is not None:
            path_str = str(project_path)
            if path_str not in sys.path:
                sys.path.insert(0, path_str)

    def compile_code(self, code: str, filename: str = "<bluep>") -> ExecutionResult:
        """Compile (syntax-check) code without executing it.

        Mirrors BlueJ's Compile action.
        """
        try:
            compile(code, filename, "exec")
            return ExecutionResult(success=True)
        except SyntaxError as e:
            return ExecutionResult(
                success=False,
                error=f"SyntaxError: {e.msg} (line {e.lineno})",
            )

    def compile_file(self, filepath: Path) -> ExecutionResult:
        """Compile a file - mirrors BlueJ's compile class."""
        return self.compile_code(filepath.read_text(), str(filepath))

    def execute_code(self, code: str, filename: str = "<bluep>",
                     capture: bool = True) -> ExecutionResult:
        """Execute code in the namespace and return the result.

        Mirrors BlueJ's running code / Code Pad evaluation.
        """
        # Redirect stdout if capture requested
        if capture:
            self._output_buffer = io.StringIO()
            self._old_stdout = sys.stdout
            sys.stdout = self._output_buffer

        try:
            # Try to compile first
            compiled = compile(code, filename, "exec")
            exec(compiled, self.namespace)
            output = self._output_buffer.getvalue() if capture else ""
            return ExecutionResult(success=True, output=output, value=None)
        except SystemExit as e:
            return ExecutionResult(
                success=True,
                output=self._output_buffer.getvalue() if capture else "",
                value=f"SystemExit({e.code})",
            )
        except Exception as e:
            tb = traceback.format_exc()
            return ExecutionResult(
                success=False,
                output=self._output_buffer.getvalue() if capture else "",
                error=f"{type(e).__name__}: {e}",
                traceback_str=tb,
            )
        finally:
            if capture:
                sys.stdout = self._old_stdout or sys.__stdout__

    def evaluate_expression(self, expression: str) -> ExecutionResult:
        """Evaluate a single expression and return its value.

        Used by the Code Pad - mirrors BlueJ's Code Pad.
        """
        self._output_buffer = io.StringIO()
        self._old_stdout = sys.stdout
        sys.stdout = self._output_buffer

        try:
            value = eval(expression, self.namespace)
            output = self._output_buffer.getvalue()
            return ExecutionResult(success=True, output=output, value=value)
        except Exception as e:
            tb = traceback.format_exc()
            return ExecutionResult(
                success=False,
                output=self._output_buffer.getvalue(),
                error=f"{type(e).__name__}: {e}",
                traceback_str=tb,
            )
        finally:
            sys.stdout = self._old_stdout or sys.__stdout__

    def instantiate(self, class_name: str, *args: Any, name: str | None = None, **kwargs: Any) -> BenchObject:
        """Create an instance of a class and place it on the bench.

        Mirrors BlueJ's 'Instantiate object' action.
        If name is provided, uses it instead of auto-generating one.
        """
        if class_name not in self.namespace:
            raise NameError(f"Class '{class_name}' not found. Compile it first.")

        cls = self.namespace[class_name]
        if not inspect.isclass(cls):
            raise TypeError(f"'{class_name}' is not a class")

        instance = cls(*args, **kwargs)
        if name:
            bench_name = name
            count = self._bench_counter.get(class_name, 0) + 1
            self._bench_counter[class_name] = count
        else:
            bench_name = self._generate_bench_name(class_name)
        bench_obj = BenchObject(name=bench_name, instance=instance, class_name=class_name)
        self.bench[bench_name] = bench_obj
        # Make the object accessible from the code pad by its bench name
        self.namespace[bench_name] = instance
        return bench_obj

    def _generate_bench_name(self, class_name: str) -> str:
        """Generate a unique name for a bench object (e.g., obj1, obj2)."""
        count = self._bench_counter.get(class_name, 0) + 1
        self._bench_counter[class_name] = count
        # BlueJ uses lowercase first letter
        base = class_name[0].lower() + class_name[1:] if class_name else "obj"
        return f"{base}{count}"

    def remove_bench_object(self, name: str) -> None:
        """Remove an object from the bench."""
        self.bench.pop(name, None)
        self.namespace.pop(name, None)

    def clear_bench(self) -> None:
        """Remove all objects from the bench."""
        for name in list(self.bench.keys()):
            self.namespace.pop(name, None)
        self.bench.clear()
        self._bench_counter.clear()

    def load_module(self, filepath: Path, module_name: str | None = None) -> ExecutionResult:
        """Load a Python file as a module into the namespace.

        This is how BlueP 'compiles' a class - it loads the .py file
        so the class becomes available for instantiation.
        """
        if module_name is None:
            module_name = filepath.stem

        source = filepath.read_text()
        return self.execute_code(source, str(filepath), capture=False)

    def get_namespace_classes(self) -> list[str]:
        """Return all class names available in the namespace."""
        return sorted(
            name for name, obj in self.namespace.items()
            if inspect.isclass(obj) and not name.startswith("_")
        )

    def get_namespace_objects(self) -> list[str]:
        """Return all non-class objects in the namespace."""
        return sorted(
            name for name, obj in self.namespace.items()
            if not inspect.isclass(obj) and not name.startswith("_")
            and not callable(obj)
        )

    def reset(self) -> None:
        """Reset the executor state."""
        self.namespace = {"__name__": "__main__", "__builtins__": __builtins__}
        self.bench.clear()
        self._bench_counter.clear()
        if self.project_path:
            self.namespace["__file__"] = str(self.project_path)

    def call_bench_method(self, bench_name: str, method_name: str,
                          *args: Any, **kwargs: Any) -> ExecutionResult:
        """Call a method on a bench object."""
        obj = self.bench.get(bench_name)
        if obj is None:
            return ExecutionResult(success=False, error=f"Object '{bench_name}' not on bench")

        self._output_buffer = io.StringIO()
        self._old_stdout = sys.stdout
        sys.stdout = self._output_buffer

        try:
            result = obj.call_method(method_name, *args, **kwargs)
            output = self._output_buffer.getvalue()
            return ExecutionResult(success=True, output=output, value=result)
        except Exception as e:
            tb = traceback.format_exc()
            return ExecutionResult(
                success=False,
                output=self._output_buffer.getvalue(),
                error=f"{type(e).__name__}: {e}",
                traceback_str=tb,
            )
        finally:
            sys.stdout = self._old_stdout or sys.__stdout__
