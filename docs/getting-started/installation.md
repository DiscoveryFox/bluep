# Installation

BlueP is available as native installers for Linux, Windows, and macOS, plus a
Python wheel for `pip`. Download the latest build from the
[Releases page](https://github.com/DiscoveryFox/bluep/releases).

## Requirements

BlueP requires:

- **Python ≥ 3.14**
- **GTK 4** (typically `gtk4` package)
- **PyGObject** (`python-gobject` or `pygobject`)
- **GtkSourceView 5** (optional but recommended for syntax highlighting,
  native auto-indent, and breakpoints — `gtksourceview5`)
- [**uv**](https://docs.astral.sh/uv/) package manager (for building from source)

!!! note "AppImage, Flatpak, Windows, and macOS bundles include GTK4"
    The AppImage, Flatpak, Windows installer, and macOS `.dmg` bundle GTK4,
    PyGObject, and GtkSourceView 5 — no manual system dependency installation is
    needed for those. System dependencies are only required for the DEB/RPM
    and `pip` wheel.

## Linux

=== "AppImage (recommended, portable)"

    No installation needed — download and run:

    ```bash
    chmod +x BlueP-*-x86_64.AppImage
    ./BlueP-*-x86_64.AppImage
    ```

=== "Flatpak"

    ```bash
    flatpak install BlueP-*-x86_64.flatpak
    flatpak run io.bluep.BlueP
    ```

=== "DEB (Debian/Ubuntu)"

    Requires Python ≥ 3.14 as the system interpreter (Fedora 43+, Arch).
    On Ubuntu LTS, use the AppImage or Flatpak instead.

    ```bash
    sudo apt install ./bluep_*_amd64.deb
    bluep
    ```

=== "RPM (Fedora/RHEL)"

    ```bash
    sudo dnf install ./bluep-*.rpm
    bluep
    ```

### System dependencies (DEB/RPM and pip only)

=== "Debian/Ubuntu"

    ```bash
    sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-gtksourceview-5
    ```

=== "Fedora"

    ```bash
    sudo dnf install python3-gobject gtk4 gtksourceview5
    ```

=== "Arch"

    ```bash
    sudo pacman -S python-gobject gtk4 gtksourceview5
    ```

## Windows

=== "Installer (recommended)"

    Download `BlueP-Setup-*.exe` and double-click to install. BlueP appears in
    the Start Menu and can associate with `.bluep` project files.

=== "Portable zip"

    ```bash
    # Unzip and run — no installation, no admin rights
    unzip BlueP-*-windows-x64.zip
    BlueP\BlueP.exe
    ```

## macOS

Download `BlueP-*-macos.dmg`, open it, and drag **BlueP** into
**Applications**.

!!! warning "Gatekeeper on first launch"
    The build is not code-signed with an Apple Developer certificate. On first
    launch you may see "BlueP cannot be opened because it is from an
    unidentified developer." Right-click the app and choose **Open** →
    **Open** to approve it once.

## pip (from GitHub)

```bash
# From a release wheel (recommended)
pip install https://github.com/DiscoveryFox/bluep/releases/download/v0.1.0/bluep-0.1.0-py3-none-any.whl

# Or from a tagged commit
pip install git+https://github.com/DiscoveryFox/bluep.git@v0.1.0
```

then run:

```bash
bluep
```

The wheel does **not** bundle GTK4 — install the system dependencies for your
platform first (see [System dependencies](#system-dependencies-debrpm-and-pip-only)
for Linux, or `brew install gtk4 pygobject3 gtksourceview5` on macOS). On
Windows, use the installer or portable zip instead — GTK4 is not pip-installable.

## Build from source

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

## Releases

New releases are built and published automatically by a GitHub Actions
workflow (`.github/workflows/release.yml`). To cut a release, go to the
**Actions** tab → **Release** → **Run workflow** and choose a version bump
level (`patch`, `minor`, or `major`). The workflow bumps the version in
`pyproject.toml`, tags the commit as `v<version>`, builds all platform
installers and the wheel, and publishes a GitHub Release with install
instructions.
