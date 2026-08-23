# BlueP {VERSION}

A BlueJ-inspired IDE for Python, built with GTK4 and PyGObject.

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

- See [commit history](https://github.com/DiscoveryFox/bluep/compare/vPREVIOUS...v{VERSION}) for changes in this release.
