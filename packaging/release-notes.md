# BlueP {VERSION}

A BlueJ-inspired IDE for Python, built with GTK4 and PyGObject.

BlueP mirrors the visual, object-oriented workflow of BlueJ — class diagrams,
an interactive object bench, instant object inspection, a code pad — and
adapts it to Python. It is designed for teaching object-oriented programming
and for rapid prototyping of class-based Python projects.

## Highlights

- **Visual class diagram** — drag-and-drop class boxes with live dependency
  arrows; create, rename, and delete classes from the diagram
- **Interactive object bench** — instantiate any class, call methods, inspect
  fields, keep live objects for experimentation
- **Code editor** — syntax-highlighted (GtkSourceView 5) with autocomplete,
  bracket auto-closing, auto-indent, line numbers, and breakpoint gutter
- **Code pad** — REPL-style scratch pad for evaluating Python expressions
  against the current project state
- **Debugger** — step-by-step debugging with variable inspection, breakpoint
  management, and call-stack view
- **AI agent panel** — optional OpenAI-compatible integration for code
  generation (disabled by default, lockable via supervised mode)
- **Supervised mode** — classroom/exam lock (`BLUEP_SUPERVISED=true`) that
  disables AI features and interpreter settings
- **Native installers** for Linux (AppImage, Flatpak, DEB, RPM), Windows
  (Inno Setup installer, portable zip), and macOS (DMG)

## Install

### Linux

**AppImage** (portable, no install needed):

```bash
chmod +x BlueP-{VERSION}-x86_64.AppImage
./BlueP-{VERSION}-x86_64.AppImage
```

**Flatpak:**

```bash
flatpak install BlueP-{VERSION}-x86_64.flatpak
flatpak run io.bluep.BlueP
```

**DEB (Debian/Ubuntu):**

```bash
sudo apt install ./bluep_{VERSION}_amd64.deb
bluep
```

**RPM (Fedora/RHEL):**

```bash
sudo dnf install ./bluep-{VERSION}-1.x86_64.rpm
bluep
```

### Windows

**Installer (recommended):**

Download `BlueP-Setup-{VERSION}.exe` and double-click to install.

**Portable zip:**

```bash
# Unzip and run
unzip BlueP-{VERSION}-windows-x64.zip
BlueP\BlueP.exe
```

### macOS

**Disk image:**

Download `BlueP-{VERSION}-macos.dmg`, open it, and drag **BlueP** into
**Applications**.

> **Note:** On macOS, the first launch may show a Gatekeeper warning
> ("unidentified developer"). Right-click the app and choose **Open** to
> approve it.

### pip (from GitHub)

```bash
pip install https://github.com/DiscoveryFox/bluep/releases/download/v{VERSION}/bluep-{VERSION}-py3-none-any.whl
```

or

```bash
pip install git+https://github.com/DiscoveryFox/bluep.git@v{VERSION}
```

then run:

```bash
bluep
```

> **System dependencies:** the pip wheel does **not** bundle GTK4.
> Linux: `sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-gtksourceview-5`
> macOS: `brew install gtk4 pygobject3 gtksourceview5`
> Windows: use the installer or portable zip instead — GTK4 is not pip-installable.

## Changelog

- See [commit history](https://github.com/DiscoveryFox/bluep/compare/v{PREVIOUS}...v{VERSION}) for changes in this release.

## System Requirements

- **Linux (DEB/RPM):** Python ≥ 3.14 as system interpreter, GTK 4, PyGObject, GtkSourceView 5
- **Linux (AppImage/Flatpak):** self-contained — no system dependencies required
- **Windows:** Windows 10 or later
- **macOS:** macOS 11 (Big Sur) or later
