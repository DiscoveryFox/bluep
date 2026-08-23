# Changelog

All notable changes to BlueP are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.3] - 2026-08-24

### Fixed

- **Bottom panel layout** — closing all panels no longer leaves the divider
  stranded mid-screen; the paned separator collapses to the bottom so the
  upper section gets maximum space and only the restore bar is visible.
  Reopening a single panel now resets the divider to a usable 60/40 split.
- **Fixed tab order** — reopened tabs now always appear in their canonical
  position (Terminal, Code Pad, Debugger, AI) regardless of the order in
  which panels were closed and reopened, using `insert_page` at a computed
  index instead of `append_page`.
- **Notebook sizing** — the 200 px minimum size request moved from
  `_bottom_box` to `_bottom_notebook` so an empty notebook doesn't reserve
  space; the notebook now has `vexpand=True` so a single reopened panel
  fills the available height instead of rendering at ~50 px.
- **Toggle action** — Ctrl+J now flips the entire bottom area visibility
  instead of no-oping when the notebook is empty.
- **AppImage build** — replaced appimage-builder with a manual AppDir +
  appimagetool workflow; switched to `--appimage-extract-and-run` to avoid
  FUSE on CI runners; pinned `pygobject==3.48.2` and added
  `libglib2.0-dev` for the Ubuntu 24.04 build; omitted
  `gir1.2-gtksourceview-5` from runtime packages; symlinked icon and
  `.desktop` file to AppDir root for appimagetool; installed runtime
  packages on the host runner before copying into AppDir; fixed apt
  sources for deadsnakes PPA and Ubuntu archive repos.
- **Release pipeline** — fixed build failures across AppImage, Windows,
  macOS, and Flatpak jobs.

### Documentation

- Added release notes with features and system requirements.

## [0.1.1] - 2026-08-22

### Features

- VSCode-style command palette (Ctrl+Shift+P) for searching and executing
  any window action by name.
- Editor restore button on the right edge; dynamic bottom panel
  close/restore with a restore bar.
- Auto-collapse bottom area and editor when all tabs are closed.
- Panel hide/show, ghost text completion, autocomplete redesign, and
  code pad sync.
- Keyboard shortcuts registered via `Gtk.Application.set_accels_for_action`
  for higher priority over widget-level bindings.
- Debugger tab auto-restores on `debug-instantiate` and breakpoint pause.
- Object bench menu positioning fix; resizable terminal panel; create-folder
  in project dialog.
