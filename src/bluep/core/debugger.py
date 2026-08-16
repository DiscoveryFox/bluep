"""Debugger for BlueP.

Implements breakpoint setting, stepping, and variable inspection using
Python's `bdb` / `sys.settrace` framework - mirroring BlueJ's debugger.

Supports:
- Line breakpoints
- Step over / step into / step out
- Continue execution
- Variable inspection at breakpoints
- Call stack display
"""

from __future__ import annotations

import bdb
import inspect
import linecache
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import FrameType


@dataclass
class Breakpoint:
    """A source code breakpoint."""
    file: str
    line: int
    enabled: bool = True
    condition: str | None = None
    hit_count: int = 0


@dataclass
class StackFrame:
    """A frame in the call stack."""
    filename: str
    function_name: str
    line_number: int
    local_vars: dict[str, str] = field(default_factory=dict)
    source_line: str = ""

    @property
    def display_name(self) -> str:
        return f"{self.function_name} ({Path(self.filename).name}:{self.line_number})"


@dataclass
class DebugState:
    """Current state of the debugger."""
    is_running: bool = False
    is_paused: bool = False
    current_file: str = ""
    current_line: int = 0
    current_function: str = ""
    call_stack: list[StackFrame] = field(default_factory=list)
    local_variables: dict[str, str] = field(default_factory=dict)
    global_variables: dict[str, str] = field(default_factory=dict)


class BluePDebugger(bdb.Bdb):
    """Custom debugger extending Python's bdb module.

    This is the core debugging engine - it hooks into Python's execution
    and pauses at breakpoints, mirroring BlueJ's debug functionality.
    """

    def __init__(self) -> None:
        super().__init__()
        self.breakpoints: dict[str, dict[int, Breakpoint]] = {}
        self.state = DebugState()
        self._stop_event = threading.Event()
        self._step_action: str = "continue"  # "step", "next", "return", "continue"
        self._pause_callback: Callable[[DebugState], None] | None = None
        self._frame: FrameType | None = None
        self._should_skip: set[str] = set()  # files to skip (stdlib etc.)

        # Skip standard library files
        stdlib_path = Path(sys.prefix) / "lib"
        self._should_skip.add(str(stdlib_path))

    def set_pause_callback(self, callback: Callable[[DebugState], None]) -> None:
        """Set the callback called when execution pauses at a breakpoint."""
        self._pause_callback = callback

    def add_breakpoint(self, filename: str, line: int, condition: str | None = None) -> None:
        """Add a breakpoint at the given file and line."""
        filename = str(Path(filename).resolve())
        if filename not in self.breakpoints:
            self.breakpoints[filename] = {}
        bp = Breakpoint(file=filename, line=line, condition=condition)
        self.breakpoints[filename][line] = bp
        # Also set in bdb
        self.set_break(filename, line, cond=condition)

    def remove_breakpoint(self, filename: str, line: int) -> None:
        """Remove a breakpoint."""
        filename = str(Path(filename).resolve())
        if filename in self.breakpoints:
            self.breakpoints[filename].pop(line, None)
            if not self.breakpoints[filename]:
                del self.breakpoints[filename]
        self.clear_break(filename, line)

    def toggle_breakpoint(self, filename: str, line: int) -> bool:
        """Toggle a breakpoint on/off. Returns new enabled state."""
        filename = str(Path(filename).resolve())
        if filename in self.breakpoints and line in self.breakpoints[filename]:
            bp = self.breakpoints[filename][line]
            if bp.enabled:
                self.remove_breakpoint(filename, line)
                return False
            else:
                bp.enabled = True
                self.set_break(filename, line)
                return True
        else:
            self.add_breakpoint(filename, line)
            return True

    def get_breakpoints(self, filename: str | None = None) -> list[Breakpoint]:
        """Get breakpoints, optionally filtered by file."""
        if filename:
            filename = str(Path(filename).resolve())
            return list(self.breakpoints.get(filename, {}).values())
        result = []
        for lines in self.breakpoints.values():
            result.extend(lines.values())
        return result

    def has_breakpoint(self, filename: str, line: int) -> bool:
        filename = str(Path(filename).resolve())
        return (filename in self.breakpoints and line in self.breakpoints[filename]
                and self.breakpoints[filename][line].enabled)

    # --- Execution control ---

    def continue_execution(self) -> None:
        """Continue execution until next breakpoint."""
        self._step_action = "continue"
        self._stop_event.set()

    def step_into(self) -> None:
        """Step into the next line (enter function calls)."""
        self._step_action = "step"
        self._stop_event.set()

    def step_over(self) -> None:
        """Step over the next line (skip function calls)."""
        self._step_action = "next"
        self._stop_event.set()

    def step_out(self) -> None:
        """Step out of the current function."""
        self._step_action = "return"
        self._stop_event.set()

    def stop_debugging(self) -> None:
        """Stop debugging entirely."""
        self._step_action = "stop"
        self._stop_event.set()
        if self.state.is_running:
            self.set_quit()

    # --- bdb overrides ---

    def user_line(self, frame: FrameType) -> None:
        """Called when a line is about to be executed."""
        filename = frame.f_code.co_filename

        # Skip if not in project files (or if no breakpoints and not stepping)
        if self._should_skip_file(filename):
            return

        line = frame.f_lineno

        # Check if we hit a breakpoint
        hit_bp = self.has_breakpoint(filename, line)

        if not hit_bp and self._step_action not in ("step", "next", "return"):
            return

        if hit_bp:
            self.breakpoints[filename][line].hit_count += 1
            # Check condition
            bp = self.breakpoints[filename][line]
            if bp.condition:
                try:
                    if not eval(bp.condition, frame.f_globals, frame.f_locals):
                        return
                except Exception:
                    pass

        self._pause_at_frame(frame)

    def user_call(self, frame: FrameType, argument_list: Any) -> None:
        """Called when a function is called."""
        if self._step_action == "step":
            self._pause_at_frame(frame)

    def user_return(self, frame: FrameType, return_value: Any) -> None:
        """Called when a function returns."""
        if self._step_action == "return":
            self._pause_at_frame(frame)

    def user_exception(self, frame: FrameType, exc_info: Any) -> None:
        """Called when an exception occurs."""
        self._pause_at_frame(frame)

    def _pause_at_frame(self, frame: FrameType) -> None:
        """Pause execution and update debugger state."""
        self.state.is_paused = True
        self.state.current_file = frame.f_code.co_filename
        self.state.current_line = frame.f_lineno
        self.state.current_function = frame.f_code.co_name

        # Build call stack
        self.state.call_stack = self._build_stack(frame)

        # Capture variables
        self.state.local_variables = {
            name: repr(value)[:200]
            for name, value in frame.f_locals.items()
            if not name.startswith("_")
        }
        self.state.global_variables = {
            name: repr(value)[:200]
            for name, value in frame.f_globals.items()
            if not name.startswith("_") and not callable(value)
            and name not in ("__builtins__", "__name__")
        }

        self._frame = frame

        # Call pause callback
        if self._pause_callback:
            self._pause_callback(self.state)

        # Wait for user to continue/step
        self._stop_event.clear()
        self._stop_event.wait()

        self.state.is_paused = False

        if self._step_action == "stop":
            self.set_quit()

    def _build_stack(self, frame: FrameType) -> list[StackFrame]:
        """Build the call stack from the current frame."""
        stack: list[StackFrame] = []
        while frame:
            filename = frame.f_code.co_filename
            if not self._should_skip_file(filename):
                local_vars = {
                    name: repr(value)[:100]
                    for name, value in frame.f_locals.items()
                    if not name.startswith("_")
                }
                source_line = linecache.getline(filename, frame.f_lineno).rstrip()
                stack.append(StackFrame(
                    filename=filename,
                    function_name=frame.f_code.co_name,
                    line_number=frame.f_lineno,
                    local_vars=local_vars,
                    source_line=source_line,
                ))
            frame = frame.f_back
        return stack

    def _should_skip_file(self, filename: str) -> bool:
        """Check if a file should be skipped during debugging."""
        if "<" in filename:  # Built-in or string
            return True
        for skip_path in self._should_skip:
            if skip_path in filename:
                return True
        return False

    def add_watch_file(self, filepath: Path) -> None:
        """Add a file that the debugger should track (project file)."""
        filepath_str = str(filepath.resolve())
        # Remove from skip list if present
        self._should_skip = {p for p in self._should_skip if p not in filepath_str}

    def run_code(self, code: str, filename: str = "<debug>", namespace: dict | None = None) -> None:
        """Run code under the debugger."""
        if namespace is None:
            namespace = {"__name__": "__main__", "__builtins__": __builtins__}
        self.state.is_running = True
        self._step_action = "continue"
        try:
            self.runctx(code, namespace, namespace, filename=filename)
        finally:
            self.state.is_running = False
            self.state.is_paused = False

    def run_call(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """Run a function call under the debugger. Blocks until done.

        Use from a background thread — _pause_at_frame blocks on _stop_event.
        """
        self.state.is_running = True
        self._step_action = "continue"
        try:
            return self.runcall(func, *args, **kwargs)
        finally:
            self.state.is_running = False
            self.state.is_paused = False

    def get_variable_value(self, name: str) -> Any | None:
        """Get a variable's value from the current frame."""
        if self._frame is None:
            return None
        if name in self._frame.f_locals:
            return self._frame.f_locals[name]
        if name in self._frame.f_globals:
            return self._frame.f_globals[name]
        return None

    def set_variable_value(self, name: str, value: Any) -> bool:
        """Set a variable's value in the current frame."""
        if self._frame is None:
            return False
        if name in self._frame.f_locals:
            self._frame.f_locals[name] = value
            return True
        if name in self._frame.f_globals:
            self._frame.f_globals[name] = value
            return True
        return False
