# PyInstaller spec for BlueP — builds a standalone GTK4 bundle on Windows and macOS.
#
# Windows  (run inside MSYS2 UCRT64 shell):
#   python -m PyInstaller --noconfirm --clean packaging/bluep.spec
# macOS    (Homebrew python + gtk4 from brew):
#   python3 -m PyInstaller --noconfirm --clean packaging/bluep.spec
#
# The spec bundles the full PyGObject ("gi") stack and pins the typelib versions
# BlueP imports, so PyInstaller pulls in the matching .typelib and DLLs.

from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_all

# SPECPATH is set by PyInstaller to the directory containing this spec file
# (packaging/). Analysis() resolves script, pathex, and datas paths relative to
# SPECPATH, not CWD — so compute the repo root to use absolute paths.
_repo_root = Path(SPECPATH).parent

# ── Collect the entire gi stack (typelibs, DLLs/dylibs, girepository) ──────────
datas, binaries, hiddenimports = collect_all("gi")

# Pin the exact typelib versions BlueP imports — see src/bluep/**/*.py
# (gi.require_version calls). Passed to Analysis() as hooksconfig so the
# built-in hook-gi.repository.* hooks bind the correct typelib versions.
gi_module_versions = {
    "Gtk": "4.0",
    "Gdk": "4.0",
    "Gio": "2.0",
    "Gsk": "4.0",
    "Graphene": "1.0",
    "Pango": "1.0",
    "GtkSource": "5",
}

# ── Bundle package data (CSS theme) ──────────────────────────────────────────
# styles.css is loaded at runtime via Path(__file__).parent / "resources".
pkg_resources = _repo_root / "src" / "bluep" / "resources"
if pkg_resources.exists():
    datas += [(str(pkg_resources), "bluep/resources")]

# Ensure bluep subpackages are picked up (hidden imports for frozen execs).
hiddenimports += [
    "bluep",
    "bluep.__main__",
    "bluep.app",
    "bluep.config",
    "bluep.core",
    "bluep.core.ai_agent",
    "bluep.core.class_info",
    "bluep.core.debugger",
    "bluep.core.executor",
    "bluep.core.project",
    "bluep.ui",
    "bluep.ui.ai_panel",
    "bluep.ui.class_diagram",
    "bluep.ui.class_editor",
    "bluep.ui.code_editor",
    "bluep.ui.code_pad",
    "bluep.ui.command_palette",
    "bluep.ui.debugger_panel",
    "bluep.ui.dialogs",
    "bluep.ui.main_window",
    "bluep.ui.object_bench",
    "bluep.ui.terminal",
]

# ── Platform-specific icon ───────────────────────────────────────────────────
icon = None
if sys.platform == "win32":
    ico = _repo_root / "packaging" / "assets" / "io.bluep.BlueP.ico"
    if ico.exists():
        icon = str(ico)
elif sys.platform == "darwin":
    icns = _repo_root / "packaging" / "assets" / "io.bluep.BlueP.icns"
    if icns.exists():
        icon = str(icns)

# ── Analysis ──────────────────────────────────────────────────────────────────
a = Analysis(
    [str(_repo_root / "src" / "bluep" / "__main__.py")],
    pathex=[str(_repo_root / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    hooksconfig={
        "gi": {
            "module-versions": gi_module_versions,
        },
    },
)

pyz = PYZ(a.pure)

# ── Windows: onedir exe + COLLECT ──────────────────────────────────────────────
if sys.platform == "win32":
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="BlueP",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,  # GUI app — no console window
        icon=icon,
    )
    COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name="BlueP",
    )
# ── macOS: onedir exe + COLLECT, then bundle into .app ─────────────────────────
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="BlueP",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        icon=icon,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name="BlueP",
    )
    BUNDLE(
        coll,
        name="BlueP.app",
        icon=icon,
        bundle_identifier="io.bluep.BlueP",
    )
