"""BlueP - A BlueJ-inspired IDE for Python.

BlueP mirrors all the functionalities of BlueJ with a modern Python
architecture stack. It provides visual class diagrams, an interactive
object bench, object inspection, a code editor, debugger, code pad,
and AI agent integration.
"""

from importlib.metadata import PackageNotFoundError, version

__all__ = ["__version__"]

try:
    # Single source of truth: pyproject.toml [project].version
    __version__: str = version("bluep")
except PackageNotFoundError:  # running from source without install
    __version__ = "0.0.0+dev"
