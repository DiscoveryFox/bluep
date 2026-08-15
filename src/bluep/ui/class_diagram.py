"""Class diagram view for BlueP.

Renders the visual class diagram with:
- Class boxes showing class name, kind, fields, and methods
- Relationship arrows (inheritance, composition, dependency)
- Draggable class boxes
- Context menus (right-click) for class operations
- Double-click to open editor
- Striped/hatched backgrounds for abstract classes (like BlueJ)

This is the central visual element of BlueP, just as the class diagram
is the central visual element of BlueJ.

Uses GTK4's Gtk.Snapshot API for rendering (no Cairo dependency).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Callable

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gtk, Gdk, GLib, GObject, Pango, Gsk, Graphene

from bluep.core.class_info import ClassInfo, ClassKind, RelationshipKind, Relationship, ProjectModel


# Colors for the Catppuccin Mocha palette
COLORS = {
    "bg": (0.118, 0.118, 0.180),       # #1e1e2e
    "box_bg": (0.192, 0.196, 0.267),   # #313244
    "box_selected": (0.271, 0.278, 0.349), # #45475a
    "box_border": (0.345, 0.353, 0.439), # #585b70
    "text": (0.804, 0.839, 0.957),     # #cdd6f4
    "text_dim": (0.631, 0.643, 0.784),  # #a6adc8
    "header_bg": (0.271, 0.278, 0.349), # #45475a
    "abstract_border": (0.976, 0.886, 0.686), # #f9e2af
    "interface_border": (0.651, 0.890, 0.631), # #a6e3a1
    "enum_border": (0.980, 0.702, 0.529), # #fab387
    "error_border": (0.953, 0.545, 0.659),  # #f38ba8
    "blue": (0.537, 0.706, 0.980),      # #89b4fa
    "green": (0.651, 0.890, 0.631),     # #a6e3a1
    "red": (0.953, 0.545, 0.659),       # #f38ba8
    "yellow": (0.976, 0.886, 0.686),    # #f9e2af
    "mauve": (0.886, 0.811, 0.910),     # #cba6f7
    "orange": (0.980, 0.702, 0.529),    # #fab387
}


def _rgba(c: tuple[float, float, float], alpha: float = 1.0) -> Gdk.RGBA:
    """Convert a color tuple to a Gdk.RGBA."""
    r = Gdk.RGBA()
    r.red, r.green, r.blue, r.alpha = c[0], c[1], c[2], alpha
    return r


def _rect(x: float, y: float, w: float, h: float) -> Graphene.Rect:
    """Create a Graphene.Rect."""
    r = Graphene.Rect()
    r.init(x, y, w, h)
    return r


def _rounded_rect(x: float, y: float, w: float, h: float, radius: float = 8) -> Gsk.RoundedRect:
    """Create a Gsk.RoundedRect."""
    rr = Gsk.RoundedRect()
    rr.init_from_rect(_rect(x, y, w, h), radius)
    return rr


def _point(x: float, y: float) -> Graphene.Point:
    """Create a Graphene.Point."""
    p = Graphene.Point()
    p.init(x, y)
    return p


def _draw_text(snapshot: Gtk.Snapshot, create_layout: Callable, text: str,
               x: float, y: float, font_desc: str, color: Gdk.RGBA) -> None:
    """Draw text at (x, y) using Pango layout."""
    layout = create_layout()
    layout.set_text(text)
    layout.set_font_description(Pango.FontDescription.from_string(font_desc))
    snapshot.save()
    snapshot.translate(_point(x, y))
    snapshot.append_layout(layout, color)
    snapshot.restore()


def _draw_centered_text(snapshot: Gtk.Snapshot, create_layout: Callable, text: str,
                         cx: float, cy: float, font_desc: str, color: Gdk.RGBA) -> None:
    """Draw text centered at (cx, cy)."""
    layout = create_layout()
    layout.set_text(text)
    layout.set_font_description(Pango.FontDescription.from_string(font_desc))
    _ink, logical = layout.get_pixel_extents()
    x = cx - logical.width / 2
    y = cy - logical.height / 2
    snapshot.save()
    snapshot.translate(_point(x, y))
    snapshot.append_layout(layout, color)
    snapshot.restore()


def _draw_line(snapshot: Gtk.Snapshot, sx: float, sy: float, tx: float, ty: float,
               width: float, color: Gdk.RGBA, dash: list[float] | None = None) -> None:
    """Draw a line from (sx, sy) to (tx, ty)."""
    pb = Gsk.PathBuilder()
    pb.move_to(sx, sy)
    pb.line_to(tx, ty)
    path = pb.to_path()
    stroke = Gsk.Stroke.new(width)
    if dash:
        stroke.set_dash(dash)
    snapshot.append_stroke(path, stroke, color)


def _fill_path(snapshot: Gtk.Snapshot, pb: Gsk.PathBuilder, color: Gdk.RGBA) -> None:
    """Close and fill a path."""
    pb.close()
    path = pb.to_path()
    snapshot.append_fill(path, Gsk.FillRule.WINDING, color)


def _stroke_path(snapshot: Gtk.Snapshot, pb: Gsk.PathBuilder, color: Gdk.RGBA,
                 width: float = 1.0) -> None:
    """Close and stroke a path."""
    pb.close()
    path = pb.to_path()
    snapshot.append_stroke(path, Gsk.Stroke.new(width), color)


class ClassBox:
    """A class box drawn on the diagram canvas.

    Each box has:
    - A header with class name and kind label
    - A fields section
    - A methods section
    - Draggable, selectable behavior
    """

    WIDTH = 180
    HEADER_HEIGHT = 36
    LINE_HEIGHT = 16
    PADDING = 8
    SECTION_GAP = 4

    def __init__(self, class_info: ClassInfo, x: float = 100, y: float = 100) -> None:
        self.class_info = class_info
        self.x = x
        self.y = y
        self.selected = False
        self.hovered = False
        self.dragging = False
        self._drag_offset_x = 0.0
        self._drag_offset_y = 0.0

    @property
    def name(self) -> str:
        return self.class_info.name

    @property
    def kind(self) -> ClassKind:
        return self.class_info.kind

    @property
    def width(self) -> float:
        return self.WIDTH

    @property
    def height(self) -> float:
        fields_count = min(len(self.class_info.instance_fields), 8) + min(len(self.class_info.class_fields), 4)
        methods_count = min(len(self.class_info.public_methods), 10) + min(len(self.class_info.constructors), 2)
        return (self.HEADER_HEIGHT +
                max(fields_count, 1) * self.LINE_HEIGHT +
                self.SECTION_GAP +
                max(methods_count, 1) * self.LINE_HEIGHT +
                self.PADDING * 2)

    def contains(self, px: float, py: float) -> bool:
        """Check if a point is inside this box."""
        return self.x <= px <= self.x + self.width and self.y <= py <= self.y + self.height

    def start_drag(self, px: float, py: float) -> None:
        self.dragging = True
        self._drag_offset_x = px - self.x
        self._drag_offset_y = py - self.y

    def update_drag(self, px: float, py: float) -> None:
        if self.dragging:
            self.x = px - self._drag_offset_x
            self.y = py - self._drag_offset_y

    def end_drag(self) -> None:
        self.dragging = False

    def get_header_center(self) -> tuple[float, float]:
        return (self.x + self.width / 2, self.y + self.HEADER_HEIGHT / 2)

    def get_top_center(self) -> tuple[float, float]:
        return (self.x + self.width / 2, self.y)

    def get_bottom_center(self) -> tuple[float, float]:
        return (self.x + self.width / 2, self.y + self.height)

    def get_left_center(self) -> tuple[float, float]:
        return (self.x, self.y + self.height / 2)

    def get_right_center(self) -> tuple[float, float]:
        return (self.x + self.width, self.y + self.height / 2)

    def render(self, snapshot: Gtk.Snapshot, create_layout: Callable) -> None:
        """Render this class box using the GTK4 snapshot API."""
        w = self.width
        h = self.height
        x = self.x
        y = self.y

        # Drop shadow
        shadow_rr = _rounded_rect(x + 2, y + 3, w, h, 8)
        snapshot.push_rounded_clip(shadow_rr)
        snapshot.append_color(_rgba((0, 0, 0), 0.3), _rect(x + 2, y + 3, w, h))
        snapshot.pop()

        # Box background
        if self.selected:
            bg = COLORS["box_selected"]
        elif self.hovered:
            bg = (0.23, 0.24, 0.32)
        else:
            bg = COLORS["box_bg"]

        box_rr = _rounded_rect(x, y, w, h, 8)
        snapshot.push_rounded_clip(box_rr)
        snapshot.append_color(_rgba(bg), _rect(x, y, w, h))
        snapshot.pop()

        # Border (color depends on kind)
        if self.class_info.has_errors:
            border_color = _rgba(COLORS["error_border"])
            dash: list[float] | None = [4, 3]
        elif self.kind == ClassKind.ABSTRACT:
            border_color = _rgba(COLORS["abstract_border"])
            dash = [6, 3]
        elif self.kind == ClassKind.INTERFACE:
            border_color = _rgba(COLORS["interface_border"])
            dash = [6, 3]
        elif self.kind == ClassKind.ENUM:
            border_color = _rgba(COLORS["enum_border"])
            dash = None
        else:
            border_color = _rgba(COLORS["box_border"])
            dash = None

        if dash:
            # Dashed border via path stroke
            pb = Gsk.PathBuilder()
            pb.add_rounded_rect(box_rr)
            path = pb.to_path()
            stroke = Gsk.Stroke.new(2.0)
            stroke.set_dash(dash)
            snapshot.append_stroke(path, stroke, border_color)
        else:
            # Solid border
            snapshot.append_border(box_rr, [2.0] * 4, [border_color] * 4)

        # Header background (rounded top corners only)
        header_rr = _rounded_rect(x, y, w, self.HEADER_HEIGHT, 8)
        snapshot.push_rounded_clip(header_rr)
        snapshot.append_color(_rgba(COLORS["header_bg"]), _rect(x, y, w, self.HEADER_HEIGHT))
        snapshot.pop()

        # Header text - class name (centered)
        _draw_centered_text(snapshot, create_layout, self.class_info.name,
                            x + w / 2, y + self.HEADER_HEIGHT / 2,
                            "Sans Bold 13", _rgba(COLORS["text"]))

        # Kind label
        kind_labels = {
            ClassKind.ABSTRACT: "\u00ababstract\u00bb",
            ClassKind.INTERFACE: "\u00abinterface\u00bb",
            ClassKind.ENUM: "\u00abenum\u00bb",
            ClassKind.DATACLASS: "\u00abdataclass\u00bb",
        }
        kind_text = kind_labels.get(self.kind, "")
        if kind_text:
            layout = create_layout()
            layout.set_text(kind_text)
            layout.set_font_description(Pango.FontDescription.from_string("Sans Italic 9"))
            _ink, logical = layout.get_pixel_extents()
            kx = x + (w - logical.width) / 2
            ky = y + self.HEADER_HEIGHT - 4 - logical.height
            snapshot.save()
            snapshot.translate(_point(kx, ky))
            snapshot.append_layout(layout, _rgba(COLORS["text_dim"]))
            snapshot.restore()

        # Divider line between header and fields
        snapshot.append_color(_rgba(COLORS["box_border"], 0.5),
                              _rect(x, y + self.HEADER_HEIGHT, w, 1))

        # Fields section
        y_cursor = y + self.HEADER_HEIGHT + self.PADDING

        # Class fields first
        for field in self.class_info.class_fields[:4]:
            prefix = "$ " if not field.is_private else "- "
            text = f"{prefix}{field.name}"
            _draw_text(snapshot, create_layout, text[:24],
                       x + self.PADDING, y_cursor, "Monospace 11",
                       _rgba(COLORS["text_dim"]))
            y_cursor += self.LINE_HEIGHT

        # Instance fields
        for field in self.class_info.instance_fields[:8]:
            prefix = "+ " if not field.is_private else "- "
            text = f"{prefix}{field.name}"
            if field.type_annotation:
                text += f" : {field.type_annotation}"
            _draw_text(snapshot, create_layout, text[:28],
                       x + self.PADDING, y_cursor, "Monospace 11",
                       _rgba(COLORS["text_dim"]))
            y_cursor += self.LINE_HEIGHT

        if not self.class_info.instance_fields and not self.class_info.class_fields:
            _draw_text(snapshot, create_layout, "(no fields)",
                       x + self.PADDING, y_cursor, "Monospace 11",
                       _rgba(COLORS["text_dim"], 0.4))
            y_cursor += self.LINE_HEIGHT

        # Divider line between fields and methods
        snapshot.append_color(_rgba(COLORS["box_border"], 0.3),
                              _rect(x, y_cursor + self.SECTION_GAP, w, 1))

        y_cursor += self.SECTION_GAP * 2

        # Methods section
        # Constructors first
        for method in self.class_info.constructors[:2]:
            text = f"+ {method.display_signature}"
            _draw_text(snapshot, create_layout, text[:30],
                       x + self.PADDING, y_cursor, "Monospace 11",
                       _rgba(COLORS["blue"]))
            y_cursor += self.LINE_HEIGHT

        # Public methods
        for method in self.class_info.public_methods[:10]:
            if method.is_constructor:
                continue
            if method.is_abstract:
                text = f"+ {method.name}() (abstract)"
                color = _rgba(COLORS["yellow"])
            else:
                text = f"+ {method.display_signature}"
                color = _rgba(COLORS["text"])
            _draw_text(snapshot, create_layout, text[:30],
                       x + self.PADDING, y_cursor, "Monospace 11", color)
            y_cursor += self.LINE_HEIGHT

        if not self.class_info.public_methods and not self.class_info.constructors:
            _draw_text(snapshot, create_layout, "(no methods)",
                       x + self.PADDING, y_cursor, "Monospace 11",
                       _rgba(COLORS["text_dim"], 0.4))
            y_cursor += self.LINE_HEIGHT

        # Compilation status indicator
        if self.class_info.has_errors:
            pb = Gsk.PathBuilder()
            pb.add_circle(_point(x + w - 10, y + 10), 4)
            path = pb.to_path()
            snapshot.append_fill(path, Gsk.FillRule.WINDING,
                                 _rgba(COLORS["error_border"]))


class ClassDiagram(Gtk.DrawingArea):
    """The class diagram view - a custom widget using GTK4 Snapshot.

    This is the central visual element of BlueP. It displays all classes
    as draggable boxes with relationship arrows, just like BlueJ's class diagram.
    """

    __gsignals__ = {
        "class-selected": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "class-double-clicked": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "class-right-clicked": (GObject.SignalFlags.RUN_FIRST, None, (str, float, float)),
        "diagram-right-clicked": (GObject.SignalFlags.RUN_FIRST, None, (float, float)),
        "class-moved": (GObject.SignalFlags.RUN_FIRST, None, (str, float, float)),
    }

    def __init__(self, model: ProjectModel) -> None:
        super().__init__()
        self.model = model
        self._boxes: dict[str, ClassBox] = {}
        self._selected: ClassBox | None = None
        self._hovered: ClassBox | None = None
        self._dragging: ClassBox | None = None
        self._drag_started = False
        self._click_start: tuple[float, float] = (0, 0)
        self._scroll_x = 0.0
        self._scroll_y = 0.0
        self._zoom = 1.0

        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_content_width(600)
        self.set_content_height(400)

        # Event handling
        ev_click = Gtk.GestureClick.new()
        ev_click.set_button(0)  # Any button
        ev_click.connect("pressed", self._on_pressed)
        ev_click.connect("released", self._on_released)
        self.add_controller(ev_click)

        ev_drag = Gtk.GestureDrag.new()
        ev_drag.connect("drag-begin", self._on_drag_begin)
        ev_drag.connect("drag-update", self._on_drag_update)
        ev_drag.connect("drag-end", self._on_drag_end)
        self.add_controller(ev_drag)

        ev_motion = Gtk.EventControllerMotion.new()
        ev_motion.connect("motion", self._on_motion)
        ev_motion.connect("leave", self._on_leave)
        self.add_controller(ev_motion)

        ev_scroll = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        ev_scroll.connect("scroll", self._on_scroll)
        self.add_controller(ev_scroll)

        self._update_boxes()

    def do_snapshot(self, snapshot: Gtk.Snapshot) -> None:
        """Render the entire diagram using the GTK4 snapshot API."""
        w = self.get_width()
        h = self.get_height()

        # Background
        snapshot.append_color(_rgba(COLORS["bg"]), _rect(0, 0, w, h))

        # Grid pattern (subtle dots)
        dot_color = _rgba((0.3, 0.31, 0.41), 0.15)
        for gx in range(0, w, 20):
            for gy in range(0, h, 20):
                snapshot.append_color(dot_color, _rect(gx - 0.5, gy - 0.5, 1.5, 1.5))

        # Draw relationships first (behind boxes)
        for rel in self.model.relationships:
            self._render_relationship(snapshot, rel)

        # Draw boxes
        for box in self._boxes.values():
            box.render(snapshot, self.create_pango_layout)

    def _update_boxes(self) -> None:
        """Sync ClassBox objects with the model."""
        existing = set(self._boxes.keys())
        current = set(self.model.classes.keys())

        # Remove deleted classes
        for name in existing - current:
            del self._boxes[name]

        new_names = current - existing
        if new_names:
            if self.model.positions_loaded:
                for name in new_names:
                    ci = self.model.classes[name]
                    self._boxes[name] = ClassBox(ci, ci.pos_x, ci.pos_y)
            else:
                occupied = [(b.x, b.y, b.width, b.height) for b in self._boxes.values()]
                for name in new_names:
                    ci = self.model.classes[name]
                    x, y = self._find_free_position(occupied, ClassBox.WIDTH)
                    ci.pos_x = x
                    ci.pos_y = y
                    self._boxes[name] = ClassBox(ci, x, y)
                    occupied.append((x, y, ClassBox.WIDTH, 136))

        # Update existing
        for name in current & existing:
            ci = self.model.classes[name]
            box = self._boxes[name]
            box.class_info = ci

    def refresh(self) -> None:
        """Refresh the diagram after model changes."""
        self._update_boxes()
        self.queue_draw()

    def _find_free_position(self, occupied: list[tuple[float, float, float, float]],
                            box_width: float, start_x: float = 20, start_y: float = 20,
                            spacing: float = 30) -> tuple[float, float]:
        """Find a non-overlapping position for a new box using a cascading grid."""
        col, row = 0, 0
        col_w = box_width + spacing
        row_h = 136 + spacing
        cols = max(1, int((self.get_width() or 400) / col_w))

        while True:
            x = start_x + col * col_w
            y = start_y + row * row_h
            overlaps = any(
                x < ox + ow + 5 and x + box_width + 5 > ox and
                y < oy + oh + 5 and y + 136 + 5 > oy
                for ox, oy, ow, oh in occupied
            )
            if not overlaps:
                return (x, y)
            col += 1
            if col >= cols:
                col = 0
                row += 1

    def set_class_position(self, name: str, x: float, y: float) -> None:
        """Move a class box to a new position."""
        if name in self._boxes:
            self._boxes[name].x = x
            self._boxes[name].y = y
            self.emit("class-moved", name, x, y)
            self.queue_draw()

    def get_selected_class(self) -> str | None:
        """Return the name of the currently selected class."""
        return self._selected.name if self._selected else None

    def select_class(self, name: str | None) -> None:
        """Select a class by name."""
        if self._selected:
            self._selected.selected = False
        if name and name in self._boxes:
            self._selected = self._boxes[name]
            self._selected.selected = True
            self.emit("class-selected", name)
        else:
            self._selected = None
        self.queue_draw()

    def _render_relationship(self, snapshot: Gtk.Snapshot, rel: Relationship) -> None:
        """Draw a relationship arrow between two classes."""
        if rel.source not in self._boxes or rel.target not in self._boxes:
            return

        src = self._boxes[rel.source]
        tgt = self._boxes[rel.target]

        # Find best connection points
        sx, sy = self._get_connection_point(src, tgt.x + tgt.width / 2, tgt.y + tgt.height / 2)
        tx, ty = self._get_connection_point(tgt, src.x + src.width / 2, src.y + src.height / 2)

        # Set line style based on relationship kind
        if rel.kind == RelationshipKind.INHERITANCE:
            line_color = _rgba(COLORS["blue"])
            dash: list[float] | None = None
        elif rel.kind == RelationshipKind.IMPLEMENTATION:
            line_color = _rgba(COLORS["green"])
            dash = [6, 3]
        elif rel.kind == RelationshipKind.COMPOSITION:
            line_color = _rgba(COLORS["mauve"])
            dash = None
        elif rel.kind == RelationshipKind.AGGREGATION:
            line_color = _rgba(COLORS["mauve"])
            dash = None
        else:
            line_color = _rgba(COLORS["text_dim"])
            dash = [4, 4]

        # Draw line
        _draw_line(snapshot, sx, sy, tx, ty, 1.5, line_color, dash)

        # Draw arrow head
        angle = math.atan2(ty - sy, tx - sx)
        arrow_len = 12
        arrow_angle = math.pi / 6

        if rel.kind in (RelationshipKind.INHERITANCE, RelationshipKind.IMPLEMENTATION):
            # Hollow triangle (inheritance/implementation)
            x1 = tx - arrow_len * math.cos(angle - arrow_angle)
            y1 = ty - arrow_len * math.sin(angle - arrow_angle)
            x2 = tx - arrow_len * math.cos(angle + arrow_angle)
            y2 = ty - arrow_len * math.sin(angle + arrow_angle)

            pb = Gsk.PathBuilder()
            pb.move_to(tx, ty)
            pb.line_to(x1, y1)
            pb.line_to(x2, y2)
            # Fill with background (hollow)
            _fill_path(snapshot, pb, _rgba(COLORS["bg"]))
            # Stroke with line color
            pb2 = Gsk.PathBuilder()
            pb2.move_to(tx, ty)
            pb2.line_to(x1, y1)
            pb2.line_to(x2, y2)
            _stroke_path(snapshot, pb2, line_color, 1.0)

        elif rel.kind == RelationshipKind.COMPOSITION:
            # Filled diamond
            dx = arrow_len * math.cos(angle)
            dy = arrow_len * math.sin(angle)
            px = tx - dx
            py = ty - dy
            half_w = 5
            perp_x = -math.sin(angle) * half_w
            perp_y = math.cos(angle) * half_w

            pb = Gsk.PathBuilder()
            pb.move_to(tx, ty)
            pb.line_to(px + perp_x, py + perp_y)
            pb.line_to(px, py)
            pb.line_to(px - perp_x, py - perp_y)
            _fill_path(snapshot, pb, _rgba(COLORS["mauve"]))

        elif rel.kind == RelationshipKind.AGGREGATION:
            # Hollow diamond
            dx = arrow_len * math.cos(angle)
            dy = arrow_len * math.sin(angle)
            px = tx - dx
            py = ty - dy
            half_w = 5
            perp_x = -math.sin(angle) * half_w
            perp_y = math.cos(angle) * half_w

            pb = Gsk.PathBuilder()
            pb.move_to(tx, ty)
            pb.line_to(px + perp_x, py + perp_y)
            pb.line_to(px, py)
            pb.line_to(px - perp_x, py - perp_y)
            # Fill with background (hollow)
            _fill_path(snapshot, pb, _rgba(COLORS["bg"]))
            # Stroke
            pb2 = Gsk.PathBuilder()
            pb2.move_to(tx, ty)
            pb2.line_to(px + perp_x, py + perp_y)
            pb2.line_to(px, py)
            pb2.line_to(px - perp_x, py - perp_y)
            _stroke_path(snapshot, pb2, _rgba(COLORS["mauve"]), 1.0)

        else:
            # Simple arrow (dependency)
            x1 = tx - arrow_len * math.cos(angle - arrow_angle)
            y1 = ty - arrow_len * math.sin(angle - arrow_angle)
            x2 = tx - arrow_len * math.cos(angle + arrow_angle)
            y2 = ty - arrow_len * math.sin(angle + arrow_angle)

            _draw_line(snapshot, tx, ty, x1, y1, 1.0, line_color)
            _draw_line(snapshot, tx, ty, x2, y2, 1.0, line_color)

        # Label
        if rel.label:
            mid_x = (sx + tx) / 2
            mid_y = (sy + ty) / 2
            layout = self.create_pango_layout(rel.label)
            layout.set_font_description(Pango.FontDescription.from_string("Sans Italic 9"))
            _ink, logical = layout.get_pixel_extents()
            snapshot.save()
            snapshot.translate(_point(mid_x - logical.width / 2, mid_y - logical.height - 2))
            snapshot.append_layout(layout, _rgba(COLORS["text_dim"]))
            snapshot.restore()

    def _get_connection_point(self, box: ClassBox, target_x: float, target_y: float) -> tuple[float, float]:
        """Get the best edge point of a box to connect to a target."""
        cx, cy = box.x + box.width / 2, box.y + box.height / 2
        dx = target_x - cx
        dy = target_y - cy

        if abs(dx) > abs(dy):
            if dx > 0:
                return box.get_right_center()
            else:
                return box.get_left_center()
        else:
            if dy > 0:
                return box.get_bottom_center()
            else:
                return box.get_top_center()

    def _get_widget_coords(self, x: float, y: float) -> tuple[float, float]:
        """Convert widget coordinates to diagram coordinates (accounting for scroll)."""
        return (x + self._scroll_x, y + self._scroll_y)

    def _find_box_at(self, x: float, y: float) -> ClassBox | None:
        """Find the class box at the given coordinates."""
        # Check in reverse order (top-most first)
        for box in reversed(list(self._boxes.values())):
            if box.contains(x, y):
                return box
        return None

    # --- Event handlers ---

    def _on_pressed(self, gesture: Gtk.GestureClick, n_press: int, x: float, y: float) -> None:
        """Handle mouse press."""
        dx, dy = self._get_widget_coords(x, y)
        self._click_start = (x, y)
        box = self._find_box_at(dx, dy)

        if box:
            # Select the box
            if self._selected:
                self._selected.selected = False
            self._selected = box
            box.selected = True
            self.emit("class-selected", box.name)

            # Start dragging
            box.start_drag(dx, dy)
            self._dragging = box
            self._drag_started = False

            # Double click
            if n_press == 2:
                self.emit("class-double-clicked", box.name)
        else:
            # Click on empty area - deselect
            if self._selected:
                self._selected.selected = False
            self._selected = None

        self.queue_draw()

    def _on_released(self, gesture: Gtk.GestureClick, n_press: int, x: float, y: float) -> None:
        """Handle mouse release."""
        button = gesture.get_current_button()

        if self._dragging:
            # If didn't actually drag, it was a click
            if not self._drag_started:
                if button == 3:  # Right click
                    dx, dy = self._get_widget_coords(x, y)
                    if self._dragging.contains(dx, dy):
                        self.emit("class-right-clicked", self._dragging.name, x, y)
            self._dragging.end_drag()
            self._dragging = None
        else:
            if button == 3:  # Right click on empty area
                self.emit("diagram-right-clicked", x, y)

        self._drag_started = False

    def _on_drag_begin(self, gesture: Gtk.GestureDrag, start_x: float, start_y: float) -> None:
        """Handle drag begin."""
        pass

    def _on_drag_update(self, gesture: Gtk.GestureDrag, offset_x: float, offset_y: float) -> None:
        """Handle drag movement."""
        if self._dragging:
            self._drag_started = True
            _success, start_x, start_y = gesture.get_start_point()
            dx, dy = self._get_widget_coords(start_x + offset_x, start_y + offset_y)
            self._dragging.update_drag(dx, dy)
            self.queue_draw()

    def _on_drag_end(self, gesture: Gtk.GestureDrag, offset_x: float, offset_y: float) -> None:
        """Handle drag end."""
        if self._dragging and self._drag_started:
            self.emit("class-moved", self._dragging.name, self._dragging.x, self._dragging.y)
        self._drag_started = False

    def _on_motion(self, controller: Gtk.EventControllerMotion, x: float, y: float) -> None:
        """Handle mouse motion for hover effects."""
        dx, dy = self._get_widget_coords(x, y)
        box = self._find_box_at(dx, dy)

        if box != self._hovered:
            if self._hovered:
                self._hovered.hovered = False
            self._hovered = box
            if box:
                box.hovered = True
                cursor = Gdk.Cursor.new_from_name("grab", None)
            else:
                cursor = Gdk.Cursor.new_from_name("default", None)
            self.set_cursor(cursor)
            self.queue_draw()

    def _on_leave(self, controller: Gtk.EventControllerMotion) -> None:
        """Handle mouse leave."""
        if self._hovered:
            self._hovered.hovered = False
            self._hovered = None
            self.queue_draw()

    def _on_scroll(self, controller: Gtk.EventControllerScroll, dx: float, dy: float) -> None:
        """Handle scroll for zoom."""
        # Could implement zoom here
        pass
