# Architecture Overview

Modus is built with Python and the [Fabric](https://github.com/Fabric-Development/fabric/)
framework (GTK/Wayland wrapper), plus custom C extensions for high-performance
Wayland interactions.

## 1. Core Application Loop

Entry point is `start.py`, delegates to `src/main.py`. `main.py` instantiates
`fabric.Application`, which manages lifecycle of floating Wayland windows:

- **Panel**: Top bar (`src/window/panel/`)
- **Dock**: macOS-style bottom dock (`src/window/dock/`)
- **Control Center**: Right-side quick settings (`src/window/controlcenter/`)
- **App Switcher**: Alt-Tab window switcher (`src/window/switcher/`)
- **Lock Screen**: Session lock (`src/window/lock.py`)
- **Spotlight Search**: Super+D search overlay (`src/window/spotlight/`)
- **Notification Center**: Notification popups and history (`src/window/notification/`)
- **OSD**: Volume/brightness overlays (`src/window/osd/`)
- **Settings**: Configuration GUI (`src/window/settings/`)
- **Wallpaper Picker**: Wallpaper browser and management (`src/window/wallpaper/`)

## 2. Spotlight Search Engine

The spotlight (`src/window/spotlight/`) is a plugin-powered search overlay.
It has three layers:

### Layer 1: UI (`main.py`)

A GTK window with an entry field and scrollable result list. Renders results
from plugins. Manages keyboard navigation, viewport sizing, and result
selection. Uses a 200ms debounce on the entry field to avoid searching on
every keystroke.

### Layer 2: Search Pipeline (`core/search.py`)

On each keystroke:

1. Routes the query — if it starts with a keyword (e.g., `gg ` for Google),
   the query goes exclusively to that plugin
2. Otherwise, dispatches to all `searchable` plugins in parallel via daemon
   threads
3. Collects results via `GLib.idle_add` (main thread callback)
4. Merges results sorted by plugin priority then result score
5. Cancels previous in-flight searches with `threading.Event` tokens

### Layer 3: Plugin System (`core/loader.py`, `core/manager.py`, `core/registry.py`)

- **Loader**: Scans `config/plugins/` for `.py` files and package directories.
  Handles per-plugin virtualenvs via `uv` for dependency isolation. Supports
  deep reload (re-import from disk without restart).
- **Manager**: Orchestrates lifecycle — instantiate, enable/disable, reload,
  release memory. Persists disabled plugin list to `plugins.json`.
- **Registry**: Stores plugin metadata keyed by id. Maintains keyword-to-plugin
  map for fast routing.

### Data flow

```
User types → debounce (200ms) → route query
  ├─ keyword match → single plugin search → render
  └─ global search → dispatch to threads → collect → merge → render

User selects result → action callback → (copy, launch, etc.)
User presses Escape → cancel searches → release plugin memory → hide
```

## 3. High-Performance App Switcher (AppCapture)

The App Switcher (Alt+Tab) needs live video previews of Wayland windows. Pure
Python DBus polling is too slow, so Modus uses a C-extension at
`src/window/switcher/app-capture/`.

- Uses `hyprland-toplevel-export-v1` Wayland protocol to get dmabuf/shm buffers
  from Hyprland
- Compiled to `libappcapture.so`, exposed to Python via GObject Introspection
- Framerate throttled by Python using `invoke_repeater`, controlled by
  `switcher_live_preview_delay_ms` in `config.toml`

## 4. Global Menu (DBus)

macOS-style menu bar in the top panel.

- Apps export menus over `com.canonical.dbusmenu` DBus
- Custom C shim (`src/window/globalmenu/libmenu_button_shim.c`) forces GTK apps to
  export menus even if they weren't designed to
- Python daemon (`src/window/globalmenu/service.py`) listens for exported menus and
  renders them as Fabric widgets in the panel

## 5. State Management & Services

Services in `src/services/` monitor system state asynchronously and emit
signals:

| Service | Source | What it tracks |
|---------|--------|---------------|
| `battery.py` | UPower over DBus | Battery percentage, charging state |
| `bluetooth.py` | BlueZ over DBus | Bluetooth devices |
| `brightness.py` | `brightnessctl` / `ddcutil` | Screen brightness |
| `network.py` | NetworkManager over DBus | WiFi, ethernet state |
| `keyboard_layout.py` | evdev / Hyprland | Keyboard layout changes |
| `nightlight.py` | Hyprland Night Light | Blue light filter state |
| `mpris.py` | MPRIS DBus | Media player state, metadata |
| `screenshot.py` | Screencapture API | Screenshot/screen recording |
| `screenrecorder.py` | `wf-recorder` | Screen recording state |
| `wallpaper.py` | Matugen / `swww` | Wallpaper changes, color generation |
| `inhibit.py` | `gtk-session-lock` | Inhibit screen lock |
| `numlock.py` | evdev | Num lock state |
| `capslock.py` | evdev | Caps lock state |
| `gamemode.py` | `gamemoded` | Game mode status |
| `todo.py` | Local JSON | Todo list items |
| `config.py` | TOML files | Config hot-reload and callbacks |

Uses signals (`connect("changed", update_ui)`) for reactive UI — virtually 0%
CPU while idle.
