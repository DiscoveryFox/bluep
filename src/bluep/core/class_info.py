"""Extract class metadata from Python source files using AST.

This module powers BlueP's class diagram by analyzing .py files and extracting
class definitions, fields, methods, inheritance relationships, and dependencies
- the same way BlueJ parses Java class files for its visual class diagram.
"""

from __future__ import annotations

import ast
import importlib.util
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import Any


class ClassKind(str, Enum):
    """The kind of class, mirroring BlueJ's class type distinctions."""
    ABSTRACT = "abstract"
    CONCRETE = "concrete"
    INTERFACE = "interface"  # ABC or Protocol
    ENUM = "enum"
    DATACLASS = "dataclass"


class RelationshipKind(str, Enum):
    """Relationship types shown in the class diagram."""
    INHERITANCE = "inheritance"
    IMPLEMENTATION = "implementation"
    COMPOSITION = "composition"
    AGGREGATION = "aggregation"
    ASSOCIATION = "association"
    DEPENDENCY = "dependency"


@dataclass
class FieldInfo:
    """A field/attribute of a class."""
    name: str
    type_annotation: str | None = None
    default_value: str | None = None
    is_class_var: bool = False
    is_private: bool = False

    @property
    def display_name(self) -> str:
        return self.name

    @property
    def display_type(self) -> str:
        return self.type_annotation or "Any"


@dataclass
class MethodInfo:
    """A method of a class."""
    name: str
    params: list[tuple[str, str | None]] = field(default_factory=list)  # (name, type)
    return_type: str | None = None
    is_static: bool = False
    is_classmethod: bool = False
    is_abstract: bool = False
    is_private: bool = False
    is_constructor: bool = False
    decorators: list[str] = field(default_factory=list)
    docstring: str | None = None

    @property
    def display_name(self) -> str:
        return self.name

    @property
    def display_signature(self) -> str:
        params_str = ", ".join(
            f"{name}: {typ}" if typ else name
            for name, typ in self.params
        )
        ret = f" -> {self.return_type}" if self.return_type else ""
        return f"{self.name}({params_str}){ret}"


@dataclass
class ClassInfo:
    """Complete metadata about a class, extracted from source.

    This is the data model behind each class box in the diagram.
    """
    name: str
    kind: ClassKind = ClassKind.CONCRETE
    bases: list[str] = field(default_factory=list)
    fields: list[FieldInfo] = field(default_factory=list)
    methods: list[MethodInfo] = field(default_factory=list)
    source_file: Path | None = None
    module_name: str | None = None
    docstring: str | None = None
    decorators: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)

    # Visual diagram state
    pos_x: float = 100.0
    pos_y: float = 100.0
    collapsed: bool = False

    @property
    def is_compiled(self) -> bool:
        """Check if the source is syntactically valid."""
        if self.source_file is None:
            return False
        try:
            ast.parse(self.source_file.read_text())
            return True
        except SyntaxError:
            return False

    @property
    def has_errors(self) -> bool:
        return not self.is_compiled

    @property
    def instance_fields(self) -> list[FieldInfo]:
        return [f for f in self.fields if not f.is_class_var]

    @property
    def class_fields(self) -> list[FieldInfo]:
        return [f for f in self.fields if f.is_class_var]

    @property
    def public_methods(self) -> list[MethodInfo]:
        return [m for m in self.methods if not m.is_private]

    @property
    def constructors(self) -> list[MethodInfo]:
        return [m for m in self.methods if m.is_constructor]


@dataclass
class Relationship:
    """A relationship between two classes in the diagram."""
    source: str  # class name
    target: str  # class name
    kind: RelationshipKind
    label: str = ""
    source_field: str | None = None  # field that establishes this relationship (for composition)


@dataclass
class ProjectModel:
    """The complete model of a BlueP project: all classes and relationships.

    This is the central data model that the class diagram visualizes and that
    the object bench / executor operate on.
    """
    name: str = "untitled"
    path: Path | None = None
    classes: dict[str, ClassInfo] = field(default_factory=dict)
    relationships: list[Relationship] = field(default_factory=list)
    positions_loaded: bool = False

    def add_class(self, info: ClassInfo) -> None:
        self.classes[info.name] = info
        self._recompute_relationships()

    def remove_class(self, name: str) -> None:
        self.classes.pop(name, None)
        self._recompute_relationships()

    def get_class(self, name: str) -> ClassInfo | None:
        return self.classes.get(name)

    def _recompute_relationships(self) -> None:
        """Rebuild relationships from class inheritance and composition info."""
        rels: list[Relationship] = []
        for cls in self.classes.values():
            for base in cls.bases:
                if base in self.classes:
                    if cls.kind == ClassKind.CONCRETE and self.classes[base].kind == ClassKind.INTERFACE:
                        rels.append(Relationship(cls.name, base, RelationshipKind.IMPLEMENTATION))
                    else:
                        rels.append(Relationship(cls.name, base, RelationshipKind.INHERITANCE))
                else:
                    # External base class - show as dependency
                    if base not in ("object", "ABC", "Protocol", "Enum", "Generic", "ABCMeta"):
                        rels.append(Relationship(cls.name, base, RelationshipKind.DEPENDENCY, base))
            # Detect composition / aggregation from field type annotations
            for f in cls.fields:
                typ = f.type_annotation or ""
                for ref_cls in self.classes:
                    if ref_cls != cls.name and ref_cls in typ:
                        rels.append(Relationship(cls.name, ref_cls, RelationshipKind.COMPOSITION, source_field=f.name))
        # Deduplicate
        seen: set[tuple[str, str, str]] = set()
        unique: list[Relationship] = []
        for r in rels:
            key = (r.source, r.target, r.kind.value)
            if key not in seen:
                seen.add(key)
                unique.append(r)
        self.relationships = unique

    def all_class_names(self) -> list[str]:
        return sorted(self.classes.keys())

    def get_relationships_for(self, class_name: str) -> list[Relationship]:
        return [r for r in self.relationships if r.source == class_name or r.target == class_name]


class ClassAnalyzer:
    """Analyzes Python source files to extract ClassInfo via AST."""

    @staticmethod
    def analyze_source(source: str, filename: Path | None = None,
                        module_name: str | None = None) -> list[ClassInfo]:
        """Parse Python source and extract all class definitions."""
        try:
            tree = ast.parse(source, filename=str(filename) if filename else "<string>")
        except SyntaxError:
            return []

        # Extract imports
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)

        classes: list[ClassInfo] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                classes.append(ClassAnalyzer._extract_class(node, filename, module_name, imports))
        return classes

    @staticmethod
    def analyze_file(filepath: Path, module_name: str | None = None) -> list[ClassInfo]:
        """Analyze a single .py file and return its class definitions."""
        source = filepath.read_text()
        if module_name is None:
            module_name = filepath.stem
        return ClassAnalyzer.analyze_source(source, filepath, module_name)

    @staticmethod
    def _extract_class(node: ast.ClassDef, source_file: Path | None,
                       module_name: str | None, imports: list[str]) -> ClassInfo:
        """Extract ClassInfo from an AST ClassDef node."""
        # Determine class kind from decorators and bases
        decorators = [ClassAnalyzer._decorator_name(d) for d in node.decorator_list]
        kind = ClassKind.CONCRETE

        # Check for ABC / Protocol (interface)
        base_names = [ClassAnalyzer._base_name(b) for b in node.bases]
        if "ABC" in base_names or "Protocol" in base_names:
            kind = ClassKind.INTERFACE
        elif "Enum" in base_names or "IntEnum" in base_names:
            kind = ClassKind.ENUM
        if "dataclass" in decorators:
            kind = ClassKind.DATACLASS

        # Check for abstractmethod
        has_abstract = False

        # Extract fields and methods
        fields: list[FieldInfo] = []
        methods: list[MethodInfo] = []

        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                # Class-level annotated assignment (e.g., x: int = 0)
                fields.append(FieldInfo(
                    name=item.target.id,
                    type_annotation=ClassAnalyzer._annotation_str(item.annotation) if item.annotation else None,
                    default_value=ast.unparse(item.value) if item.value else None,
                    is_class_var=True,
                    is_private=item.target.id.startswith("_"),
                ))
            elif isinstance(item, ast.Assign):
                # Class-level assignment (e.g., x = 0)
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        fields.append(FieldInfo(
                            name=target.id,
                            type_annotation=None,
                            default_value=ast.unparse(item.value) if item.value else None,
                            is_class_var=True,
                            is_private=target.id.startswith("_"),
                        ))
            elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method = ClassAnalyzer._extract_method(item)
                if method.is_abstract:
                    has_abstract = True
                methods.append(method)

        # If has abstract methods, mark as abstract
        if has_abstract and kind == ClassKind.CONCRETE:
            kind = ClassKind.ABSTRACT

        if kind == ClassKind.INTERFACE and ("ABC" in base_names or "Protocol" in base_names):
            if methods and not all(m.is_abstract for m in methods):
                kind = ClassKind.ABSTRACT

        # Extract instance fields from __init__ method
        init_method = next((m for m in methods if m.is_constructor), None)
        if init_method:
            init_node = next(
                (n for n in node.body
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and n.name == "__init__"),
                None
            )
            if init_node:
                for stmt in ast.walk(init_node):
                    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Attribute):
                        if isinstance(stmt.target.value, ast.Name) and stmt.target.value.id == "self":
                            fields.append(FieldInfo(
                                name=stmt.target.attr,
                                type_annotation=ClassAnalyzer._annotation_str(stmt.annotation) if stmt.annotation else None,
                                is_class_var=False,
                                is_private=stmt.target.attr.startswith("_"),
                            ))
                    elif isinstance(stmt, ast.Assign):
                        for target in stmt.targets:
                            if (isinstance(target, ast.Attribute)
                                    and isinstance(target.value, ast.Name)
                                    and target.value.id == "self"):
                                fields.append(FieldInfo(
                                    name=target.attr,
                                    type_annotation=None,
                                    default_value=ast.unparse(stmt.value) if stmt.value else None,
                                    is_class_var=False,
                                    is_private=target.attr.startswith("_"),
                                ))

        # Get docstring
        docstring = ast.get_docstring(node)

        return ClassInfo(
            name=node.name,
            kind=kind,
            bases=base_names,
            fields=fields,
            methods=methods,
            source_file=source_file,
            module_name=module_name,
            docstring=docstring,
            decorators=decorators,
            imports=imports,
        )

    @staticmethod
    def _extract_method(node: ast.FunctionDef | ast.AsyncFunctionDef) -> MethodInfo:
        """Extract MethodInfo from an AST FunctionDef node."""
        decorators = [ClassAnalyzer._decorator_name(d) for d in node.decorator_list]
        is_static = "staticmethod" in decorators
        is_classmethod = "classmethod" in decorators
        is_abstract = "abstractmethod" in decorators
        is_constructor = node.name == "__init__"
        is_private = node.name.startswith("_") and not node.name.startswith("__")
        if node.name.startswith("__") and node.name.endswith("__") and node.name != "__init__":
            is_private = False  # dunder methods are not "private"

        # Extract params (skip self/cls)
        params: list[tuple[str, str | None]] = []
        args = node.args
        skip_first = 0
        if not is_static and args.args:
            if is_classmethod:
                skip_first = 1  # cls
            elif args.args[0].arg == "self":
                skip_first = 1

        for arg in args.args[skip_first:]:
            typ = None
            if arg.annotation:
                typ = ClassAnalyzer._annotation_str(arg.annotation)
            params.append((arg.arg, typ))

        # Var arg (*args, **kwargs)
        if args.vararg:
            params.append((f"*{args.vararg.arg}", None))
        if args.kwarg:
            params.append((f"**{args.kwarg.arg}", None))

        # Return type
        return_type = None
        if node.returns:
            return_type = ClassAnalyzer._annotation_str(node.returns)

        docstring = ast.get_docstring(node)

        return MethodInfo(
            name=node.name,
            params=params,
            return_type=return_type,
            is_static=is_static,
            is_classmethod=is_classmethod,
            is_abstract=is_abstract,
            is_private=is_private,
            is_constructor=is_constructor,
            decorators=decorators,
            docstring=docstring,
        )

    @staticmethod
    def _annotation_str(annotation: ast.AST) -> str:
        """Convert an AST annotation to a readable type string."""
        try:
            return ast.unparse(annotation)
        except Exception:
            return "Any"

    @staticmethod
    def _base_name(base: ast.AST) -> str:
        """Extract the base class name from an AST expression."""
        if isinstance(base, ast.Name):
            return base.id
        if isinstance(base, ast.Attribute):
            return base.attr
        if isinstance(base, ast.Subscript):
            return ClassAnalyzer._base_name(base.value)
        try:
            return ast.unparse(base)
        except Exception:
            return "object"

    @staticmethod
    def _decorator_name(dec: ast.AST) -> str:
        """Extract decorator name."""
        if isinstance(dec, ast.Name):
            return dec.id
        if isinstance(dec, ast.Attribute):
            return dec.attr
        if isinstance(dec, ast.Call):
            return ClassAnalyzer._decorator_name(dec.func)
        try:
            return ast.unparse(dec)
        except Exception:
            return ""


def create_default_template(class_name: str, kind: ClassKind = ClassKind.CONCRETE) -> str:
    """Create a default Python class template (like BlueJ's New Class dialog)."""
    if kind == ClassKind.INTERFACE:
        return f'''"""Class {class_name} - an abstract interface."""

from abc import ABC, abstractmethod


class {class_name}(ABC):
    """{class_name} interface."""

    @abstractmethod
    def execute(self) -> None:
        """Execute the {class_name} operation."""
        ...
'''

    if kind == ClassKind.ENUM:
        return f'''"""Class {class_name} - an enumeration."""

from enum import Enum


class {class_name}(Enum):
    """{class_name} enumeration."""

    pass
'''

    if kind == ClassKind.ABSTRACT:
        return f'''"""Class {class_name} - an abstract class."""

from abc import ABC, abstractmethod


class {class_name}(ABC):
    """{class_name} abstract class."""

    def __init__(self) -> None:
        """Initialize {class_name}."""
        self._field: str = ""

    @abstractmethod
    def execute(self) -> None:
        """Execute the {class_name} operation."""
        ...
'''

    # Concrete / dataclass
    return f'''"""Class {class_name}."""


class {class_name}:
    """{class_name} class."""

    def __init__(self, name: str = "") -> None:
        """Initialize {class_name}.

        Args:
            name: The name of this instance.
        """
        self.name = name

    def get_name(self) -> str:
        """Return the name."""
        return self.name

    def set_name(self, name: str) -> None:
        """Set the name.

        Args:
            name: The new name.
        """
        self.name = name

    def __str__(self) -> str:
        return f"{class_name}({{self.name!r}})"

    def __repr__(self) -> str:
        return self.__str__()
'''
