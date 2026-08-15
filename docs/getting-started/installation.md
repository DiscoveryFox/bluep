# Installation

## Prerequisites

BlueP requires:

- **Python ≥ 3.14**
- **GTK 4** (typically `gtk4` package)
- **PyGObject** (`python-gobject` or `pygobject`)
- **GtkSourceView 5** (optional but recommended for syntax highlighting,
  native auto-indent, and breakpoints — `gtksourceview5`)
- [**uv**](https://docs.astral.sh/uv/) package manager

## System dependencies

=== "Debian/Ubuntu"

    ```bash
    sudo apt install gtk4 libgtksourceview-5-dev python3-gi
    ```

=== "Fedora"

    ```bash
    sudo dnf install gtk4 gtksourceview5 python3-gobject
    ```

=== "Arch"

    ```bash
    sudo pacman -S gtk4 gtksourceview5 python-gobject
    ```

=== "macOS (Homebrew)"

    ```bash
    brew install gtk4 gtksourceview5 pygobject3
    ```

## Install BlueP

BlueP uses `uv` — no manual dependency installation step is needed:

```bash
git clone https://github.com/DiscoveryFox/bluep.git
cd bluep
uv run bluep
```

`uv` resolves and installs the Python dependencies into an isolated virtual
environment automatically on first run.

## Verify the installation

```bash
uv run bluep --help
```

If the application window appears, the installation is working. If
GtkSourceView is not found, the editor falls back to a plain `Gtk.TextView`
with reduced features (no syntax highlighting, no breakpoints).
