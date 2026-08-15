"""Project management for BlueP.

A BlueP project is a directory containing Python source files, similar to
how a BlueJ project is a directory containing Java files plus a bluej.pkg file.

BlueP stores project metadata in a `.bluep` directory (like BlueJ's `bluej.pkg`).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

from bluep.core.class_info import (
    ClassInfo,
    ClassKind,
    ClassAnalyzer,
    ProjectModel,
    create_default_template,
)


# BlueP project metadata directory (like bluej.pkg)
BLUEP_DIR = ".bluep"
PROJECT_FILE = "project.json"
DIAGRAM_FILE = "diagram.json"


class Project:
    """A BlueP project.

    Manages source files, class metadata, diagram state, and persistence.
    """

    def __init__(self, path: Path, name: str = "untitled") -> None:
        self.path = path
        self.name = name
        self.model = ProjectModel(name=name, path=path)
        self._changed = False

    @property
    def bluep_dir(self) -> Path:
        return self.path / BLUEP_DIR

    @property
    def project_file(self) -> Path:
        return self.bluep_dir / PROJECT_FILE

    @property
    def diagram_file(self) -> Path:
        return self.bluep_dir / DIAGRAM_FILE

    @property
    def is_changed(self) -> bool:
        return self._changed

    # --- Creation / Opening ---

    @classmethod
    def create(cls, path: Path, name: str | None = None) -> Project:
        """Create a new project at the given path."""
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        name = name or path.name
        project = cls(path, name)
        project.bluep_dir.mkdir(exist_ok=True)
        project._write_metadata()
        project._write_diagram()
        project._changed = False
        return project

    @classmethod
    def open(cls, path: Path) -> Project:
        """Open an existing project."""
        path = Path(path)
        if not cls._is_bluep_project(path):
            # If not a BlueP project, adopt the directory
            return cls._adopt_directory(path)

        metadata = cls._read_metadata(path)
        name = metadata.get("name", path.name)
        project = cls(path, name)

        # Load all .py files
        project._load_classes()
        project._load_diagram_state()
        return project

    @staticmethod
    def _is_bluep_project(path: Path) -> bool:
        return (path / BLUEP_DIR / PROJECT_FILE).exists()

    @classmethod
    def _adopt_directory(cls, path: Path) -> Project:
        """Adopt an existing directory as a BlueP project."""
        project = cls(path, path.name)
        project.bluep_dir.mkdir(exist_ok=True)
        project._write_metadata()
        project._write_diagram()
        project._load_classes()
        project._changed = False
        return project

    # --- Class file management ---

    def add_class_file(self, class_name: str, kind: ClassKind = ClassKind.CONCRETE,
                       source: str | None = None) -> ClassInfo:
        """Create a new class file in the project (like BlueJ's New Class)."""
        if source is None:
            source = create_default_template(class_name, kind)

        filepath = self.path / f"{class_name}.py"
        filepath.write_text(source)
        return self._analyze_and_add(filepath)

    def add_class_from_source(self, class_name: str, source: str) -> list[ClassInfo]:
        """Add a class from source code. May create multiple ClassInfo if file has multiple classes."""
        filepath = self.path / f"{class_name}.py"
        filepath.write_text(source)
        return self._analyze_and_add_all(filepath)

    def remove_class(self, class_name: str) -> None:
        """Remove a class from the project (delete its file)."""
        cls_info = self.model.get_class(class_name)
        if cls_info and cls_info.source_file:
            cls_info.source_file.unlink(missing_ok=True)
        self.model.remove_class(class_name)
        self._changed = True

    def rename_class(self, old_name: str, new_name: str) -> None:
        """Rename a class (rename its file and class definition in source)."""
        cls_info = self.model.get_class(old_name)
        if cls_info is None or cls_info.source_file is None:
            return

        old_file = cls_info.source_file
        new_file = self.path / f"{new_name}.py"
        source = old_file.read_text()

        # Replace class definition name
        import re
        source = re.sub(
            rf'\bclass\s+{re.escape(old_name)}\b',
            f'class {new_name}',
            source
        )

        new_file.write_text(source)
        old_file.unlink(missing_ok=True)

        # Re-analyze
        self.model.remove_class(old_name)
        self._analyze_and_add(new_file)
        self._changed = True

    def update_class_source(self, class_name: str, source: str) -> None:
        """Update the source code of a class."""
        cls_info = self.model.get_class(class_name)
        if cls_info and cls_info.source_file:
            cls_info.source_file.write_text(source)
            self._analyze_and_add(cls_info.source_file)
            self._changed = True

    def get_class_source(self, class_name: str) -> str:
        """Get the source code of a class."""
        cls_info = self.model.get_class(class_name)
        if cls_info and cls_info.source_file:
            return cls_info.source_file.read_text()
        return ""

    # --- Persistence ---

    def save(self) -> None:
        """Save project metadata and diagram state."""
        self._write_metadata()
        self._write_diagram()
        self._changed = False

    def save_as(self, new_path: Path) -> None:
        """Save project to a new location."""
        new_path = Path(new_path)
        new_path.mkdir(parents=True, exist_ok=True)

        # Copy all .py files
        for py_file in self.path.glob("*.py"):
            shutil.copy2(py_file, new_path / py_file.name)

        self.path = new_path
        self.model.path = new_path
        self.bluep_dir.mkdir(exist_ok=True)
        self.save()

    # --- Internal helpers ---

    def _load_classes(self) -> None:
        """Load all .py files and analyze classes."""
        for py_file in sorted(self.path.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            self._analyze_and_add_all(py_file)

    def _analyze_and_add(self, filepath: Path) -> ClassInfo:
        """Analyze a file and add its primary class to the model."""
        classes = ClassAnalyzer.analyze_file(filepath)
        if classes:
            self.model.add_class(classes[0])
            # Add any additional classes from the same file
            for cls in classes[1:]:
                self.model.add_class(cls)
            return classes[0]
        return ClassInfo(name=filepath.stem, source_file=filepath)

    def _analyze_and_add_all(self, filepath: Path) -> list[ClassInfo]:
        """Analyze a file and add ALL its classes to the model."""
        classes = ClassAnalyzer.analyze_file(filepath)
        for cls in classes:
            self.model.add_class(cls)
        if not classes:
            # Empty or invalid file - add as a placeholder
            self.model.add_class(ClassInfo(name=filepath.stem, source_file=filepath))
        return classes

    def _write_metadata(self) -> None:
        data = {
            "name": self.name,
            "bluep_version": "1.0.0",
            "classes": [
                {
                    "name": ci.name,
                    "kind": ci.kind.value,
                    "file": ci.source_file.name if ci.source_file else None,
                }
                for ci in self.model.classes.values()
            ],
        }
        self.bluep_dir.mkdir(exist_ok=True)
        self.project_file.write_text(json.dumps(data, indent=2))

    def _write_diagram(self) -> None:
        data = {
            "classes": {
                name: {"x": ci.pos_x, "y": ci.pos_y}
                for name, ci in self.model.classes.items()
            }
        }
        self.bluep_dir.mkdir(exist_ok=True)
        self.diagram_file.write_text(json.dumps(data, indent=2))

    def _load_diagram_state(self) -> None:
        if not self.diagram_file.exists():
            return
        try:
            data = json.loads(self.diagram_file.read_text())
            positions = data.get("classes", {})
            any_explicit = False
            for name, pos in positions.items():
                if name in self.model.classes:
                    x = pos.get("x", 100.0)
                    y = pos.get("y", 100.0)
                    self.model.classes[name].pos_x = x
                    self.model.classes[name].pos_y = y
                    if x != 100.0 or y != 100.0:
                        any_explicit = True
            self.model.positions_loaded = any_explicit
        except (json.JSONDecodeError, KeyError):
            pass

    @staticmethod
    def _read_metadata(path: Path) -> dict[str, Any]:
        filepath = path / BLUEP_DIR / PROJECT_FILE
        if not filepath.exists():
            return {}
        try:
            return json.loads(filepath.read_text())
        except json.JSONDecodeError:
            return {}

    def set_class_position(self, class_name: str, x: float, y: float) -> None:
        """Update the visual position of a class in the diagram."""
        cls = self.model.get_class(class_name)
        if cls:
            cls.pos_x = x
            cls.pos_y = y
            self._changed = True

    def get_source_files(self) -> list[Path]:
        """Return all .py source files in the project."""
        return sorted(self.path.glob("*.py"))

    def mark_changed(self) -> None:
        self._changed = True
