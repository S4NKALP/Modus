# Configuration Guide

Modus is highly configurable using TOML files located in the `config/` directory.

## File Overview

| File | Purpose |
|------|---------|
| `config.toml` | Main application configuration (modules, features, toggles). |
| `mods.toml` | Custom panel button definitions (menus, shell commands). |
| `dock.toml` | Pinned applications for the dock. |

---

## `config.toml` (Main Settings)

The `config.toml` file controls which widgets and services are enabled. Most changes here require restarting Modus (`uv run start`).

**Key Settings:**
- `wallpapers_dir`: Path to the directory where your wallpapers are stored.
- `dock_enabled`: Toggle the dock widget (`true`/`false`).
- `dock_auto_hide`: Whether the dock hides automatically when windows overlap it.
- `notification_timeout`: Duration before a notification automatically dismisses (e.g., `"5s"`).
- `notification_ignored_apps`: Array of app names whose notifications should be suppressed.
- `weather_location`: Set your city for the weather widget (e.g., `"Patan, Nepal"`).

**App Switcher & Screencapture:**
- `window_switcher`: Enables the custom Alt-Tab window switcher.
- `switcher_live_preview`: Enables real-time Wayland video previews of running applications.
- `switcher_live_preview_delay_ms`: Framerate delay for previews (e.g., `200` = ~5fps). Lower is smoother but uses more CPU.
- `osd`: Enables on-screen displays for volume and brightness changes.

**Spotlight Search Keybinds** (defined in `config/hypr/modus.lua`):

| Key | Action |
|-----|--------|
| `Super + D` | Open spotlight search (default) |
| `Super + E` | Open emoji picker |
| `Super + V` | Open clipboard history |
| `Super + W` | Open wallpaper browser |
| `Alt + Shift + W` | Set random wallpaper |

These can be customized in `config/hypr/modus.lua`. The spotlight `.toggle()`
method accepts optional arguments to pre-fill keywords: `toggle('em')` opens
the emoji picker directly.

---

## `mods.toml` (Custom Panel Buttons)

You can define custom buttons for the top panel that run shell commands or show dropdown menus. **Changes to this file reload instantly!**

```toml
[Mods.terminal]
icon = "terminal.svg"
icon-size = 16
order = 1
on-clicked = "kitty"

[Mods.color-picker]
icon = "misc/color-picker.svg"
icon-size = 22
order = 0
on-left = "hyprpicker -a -n -f hex | wl-copy"
on-right = "hyprpicker -n -f hsv | wl-copy"
```

**Properties:**
- `icon`: The name of an SVG icon placed in `src/assets/icons/`.
- `icon-size`: Defaults to 16.
- `order`: Determines left-to-right position (lower numbers appear first).
- `on-clicked`, `on-left`, `on-right`, `on-middle`: Shell commands executed via `sh -c`. Supports complex piping `|` and `&&`.

---

## `dock.toml` (Pinned Apps)

Controls which applications are permanently pinned to the dock.
```toml
pinned = [
    "firefox",
    "kitty",
    "org.gnome.Nautilus"
]
```
Ensure you use the exact `.desktop` file name or application ID.
