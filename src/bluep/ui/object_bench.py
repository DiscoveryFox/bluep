"""Object bench widget for BlueP.

Displays live objects as draggable tiles at the bottom of the main window.
Right-click shows method call / inspect / remove menu (like BlueJ).
Objects can be dragged to reorder and clicked to pass as method parameters.

Mirrors BlueJ's object bench functionality.

Uses GTK4's Gtk.Snapshot API for rendering (no Cairo dependency).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gtk, Gdk, GLib, GObject, Pango, Gsk, Graphene

from bluep.core.executor import BenchObject


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


def _rounded_rect(x: float, y: float, w: float, h: float, radius: float = 6) -> Gsk.RoundedRect:
    """Create a Gsk.RoundedRect."""
    rr = Gsk.RoundedRect()
    rr.init_from_rect(_rect(x, y, w, h), radius)
    return rr


def _point(x: float, y: float) -> Graphene.Point:
    """Create a Graphene.Point."""
    p = Graphene.Point()
    p.init(x, y)
    return p


def _draw_centered_text(widget: Gtk.Widget, snapshot: Gtk.Snapshot, text: str,
                       cx: float, cy: float, font_desc: str, color: Gdk.RGBA) -> None:
    """Draw text centered at (cx, cy) using Pango layout."""
    layout = widget.create_pango_layout(text)
    layout.set_font_description(Pango.FontDescription.from_string(font_desc))
    _ink, logical = layout.get_pixel_extents()
    snapshot.save()
    snapshot.translate(_point(cx - logical.width / 2, cy - logical.height / 2))
    snapshot.append_layout(layout, color)
    snapshot.restore()


class ObjectTile(Gtk.DrawingArea):
    """A single object tile on the bench - like BlueJ's red object boxes."""

    __gsignals__ = {
        "clicked": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "right-clicked": (GObject.SignalFlags.RUN_FIRST, None, (float, float)),
        "double-clicked": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "drag-started": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    WIDTH = 120
    HEIGHT = 56

    def __init__(self, bench_object: BenchObject, index: int) -> None:
        super().__init__()
        self.bench_object = bench_object
        self.index = index
        self.selected = False
        self.hovered = False
        self._offset_x = index * (self.WIDTH + 8)

        self.set_size_request(self.WIDTH, self.HEIGHT)
        self.set_content_width(self.WIDTH)
        self.set_content_height(self.HEIGHT)

        # Events
        click = Gtk.GestureClick.new()
        click.set_button(0)
        click.connect("pressed", self._on_pressed)
        click.connect("released", self._on_released)
        self.add_controller(click)

        motion = Gtk.EventControllerMotion.new()
        motion.connect("enter", self._on_enter)
        motion.connect("leave", self._on_leave)
        self.add_controller(motion)

    def do_measure(self, orientation: Gtk.Orientation, for_size: int) -> tuple[int, int, int, int]:
        if orientation == Gtk.Orientation.HORIZONTAL:
            return (self.WIDTH, self.WIDTH, -1, -1)
        return (self.HEIGHT, self.HEIGHT, -1, -1)

    def do_snapshot(self, snapshot: Gtk.Snapshot) -> None:
        """Render the object tile using the GTK4 snapshot API."""
        w = float(self.WIDTH)
        h = float(self.HEIGHT)

        # Shadow
        shadow_rr = _rounded_rect(2, 3, w, h, 6)
        snapshot.push_rounded_clip(shadow_rr)
        snapshot.append_color(_rgba((0, 0, 0), 0.3), _rect(2, 3, w, h))
        snapshot.pop()

        # Background - red like BlueJ
        if self.selected:
            bg = (0.40, 0.20, 0.20)
        elif self.hovered:
            bg = (0.50, 0.25, 0.22)
        else:
            bg = (0.60, 0.15, 0.15)

        tile_rr = _rounded_rect(0, 0, w, h, 6)
        snapshot.push_rounded_clip(tile_rr)
        snapshot.append_color(_rgba(bg), _rect(0, 0, w, h))
        snapshot.pop()

        # Border
        if self.selected:
            border_color = _rgba((0.54, 0.71, 0.98))  # blue
        else:
            border_color = _rgba((0.35, 0.35, 0.44))
        snapshot.append_border(tile_rr, [1.5] * 4, [border_color] * 4)

        # Object name (instance name) - bold, centered
        _draw_centered_text(self, snapshot, self.bench_object.name,
                            w / 2, 14, "Sans Bold 13", _rgba((1.0, 1.0, 1.0)))

        # Class name - smaller, dim, italic, centered
        _draw_centered_text(self, snapshot, self.bench_object.class_name,
                            w / 2, 32, "Sans Italic 10", _rgba((0.85, 0.85, 0.85), 0.8))

        # Instance icon (small green circle)
        pb = Gsk.PathBuilder()
        pb.add_circle(_point(w - 12, 12), 3)
        path = pb.to_path()
        snapshot.append_fill(path, Gsk.FillRule.WINDING,
                             _rgba((0.65, 0.89, 0.63), 0.8))

    def _on_pressed(self, gesture: Gtk.GestureClick, n_press: int, x: float, y: float) -> None:
        button = gesture.get_current_button()
        if button == 3:  # Right click
            self.emit("right-clicked", x, y)
        elif button == 1:  # Left click
            self.selected = True
            self.queue_draw()
            if n_press == 2:
                self.emit("double-clicked")
            else:
                self.emit("clicked")

    def _on_released(self, gesture: Gtk.GestureClick, n_press: int, x: float, y: float) -> None:
        pass

    def _on_enter(self, controller: Gtk.EventControllerMotion, x: float, y: float) -> None:
        self.hovered = True
        self.queue_draw()

    def _on_leave(self, controller: Gtk.EventControllerMotion) -> None:
        self.hovered = False
        self.queue_draw()


class ObjectBench(Gtk.Box):
    """The object bench - a horizontal strip showing live objects.

    Mirrors BlueJ's object bench: objects appear as red tiles, right-click
    for method/inspect/remove menu, double-click to inspect.
    """

    __gsignals__ = {
        "object-selected": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "object-double-clicked": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
        "object-right-clicked": (GObject.SignalFlags.RUN_FIRST, None, (str, float, float)),
        "bench-right-clicked": (GObject.SignalFlags.RUN_FIRST, None, (float, float)),
    }

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.set_homogeneous(False)
        self.add_css_class("bluep-object-bench")
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.set_margin_start(8)
        self.set_margin_end(8)

        self._tiles: dict[str, ObjectTile] = {}
        self._selected: str | None = None

        # Empty state label
        self._empty_label = Gtk.Label.new("(Object Bench - create objects by right-clicking a class)")
        self._empty_label.add_css_class("bluep-status-bar")
        self._empty_label.set_hexpand(True)
        self._empty_label.set_halign(Gtk.Align.CENTER)
        self._empty_label.set_margin_top(16)
        self._empty_label.set_margin_bottom(16)
        self.append(self._empty_label)

        # Right-click on empty bench
        click = Gtk.GestureClick.new()
        click.set_button(3)
        click.connect("pressed", self._on_bench_right_click)
        self.add_controller(click)

    def add_object(self, bench_object: BenchObject) -> None:
        """Add an object to the bench."""
        if self._empty_label.get_parent() is not None:
            self.remove(self._empty_label)

        tile = ObjectTile(bench_object, len(self._tiles))
        tile.connect("clicked", lambda t: self._on_tile_clicked(t.bench_object.name))
        tile.connect("right-clicked", lambda t, x, y: self._on_tile_right_clicked(t.bench_object.name, x, y))
        tile.connect("double-clicked", lambda t: self._on_tile_double_clicked(t.bench_object.name))
        self._tiles[bench_object.name] = tile
        self.append(tile)
        tile.queue_draw()

    def remove_object(self, name: str) -> None:
        """Remove an object from the bench."""
        if name in self._tiles:
            self.remove(self._tiles[name])
            del self._tiles[name]
            if self._selected == name:
                self._selected = None
        if not self._tiles and self._empty_label.get_parent() is None:
            self.append(self._empty_label)

    def clear(self) -> None:
        """Clear all objects."""
        for tile in list(self._tiles.values()):
            self.remove(tile)
        self._tiles.clear()
        self._selected = None
        if self._empty_label.get_parent() is None:
            self.append(self._empty_label)

    def select_object(self, name: str) -> None:
        """Select an object by name."""
        for tile_name, tile in self._tiles.items():
            tile.selected = (tile_name == name)
            tile.queue_draw()
        self._selected = name
        self.emit("object-selected", name)

    def get_selected(self) -> str | None:
        return self._selected

    def get_object_names(self) -> list[str]:
        return list(self._tiles.keys())

    def _on_tile_clicked(self, name: str) -> None:
        self.select_object(name)

    def _on_tile_right_clicked(self, name: str, x: float, y: float) -> None:
        self.select_object(name)
        # Get absolute position
        tile = self._tiles[name]
        # Translate to bench coordinates
        alloc = tile.get_allocation()
        self.emit("object-right-clicked", name, alloc.x + x, alloc.y + y)

    def _on_tile_double_clicked(self, name: str) -> None:
        self.select_object(name)
        self.emit("object-double-clicked", name)

    def _on_bench_right_click(self, gesture: Gtk.GestureClick, n_press: int, x: float, y: float) -> None:
        self.emit("bench-right-clicked", x, y)
