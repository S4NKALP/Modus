# Configuration Guide

Modus is configured via TOML files in the `config/` directory, plus a graphical Settings window.

## File Overview

| File | Purpose | Reload |
|------|---------|--------|
| `config.toml` | Main settings (features, widgets, paths) | Restart |
| `mods.toml` | Custom panel buttons (menus, shell commands) | Instant |
| `dock.toml` | Pinned dock apps | Restart |
| `desktop.toml` | Desktop widget positions (per-monitor) | Restart |
| `config/desktop/*.py` | User desktop widgets | Instant (live reload) |

## Settings Window

Press `Super + I` to open the Settings window. It provides a GUI for most `config.toml` options organized into tabs:

- **General**: Debug mode, weather location, keyboard layouts, night light, switcher preview
- **Dock**: Enable/disable, auto-hide, icon size, special workspace apps
- **Panel**: All panel widgets (global menu, systray, control center, etc.), wallpapers directory
- **Notifications**: Timeout, ignored apps, limited history apps

Changes save to `config.toml` immediately. Some settings require a restart.

You can also toggle settings from the terminal:

```bash
fabric-cli exec modus "settings.toggle()"
```

---

## `config.toml` (Main Settings)

Auto-generated on first run with sensible defaults. Most changes require restarting Modus (`uv run start`).

Config is organized into sections. Values are accessed via dot notation (e.g. `panel.battery`).

### `[general]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `debug` | bool | `false` | Enable verbose logging |
| `weather_location` | string | `""` | City for weather widget (e.g., `"London, UK"`) |
| `keyboard_layouts` | array | `["us"]` | Active keyboard layouts |
| `wallpapers_dir` | string | `"src/assets/wallpaper_example/"` | Path to wallpapers folder |

### `[dock]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | bool | `true` | Show the dock |
| `auto_hide` | bool | `true` | Hide when windows overlap |
| `always_occluded` | bool | `false` | Keep dock behind windows |
| `icon_size` | int | `52` | Icon size in pixels |
| `hide_special_workspace_apps` | bool | `true` | Hide special workspace apps |

### `[panel]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `imac_button` | bool | `true` | Apple logo button |
| `systray` | bool | `true` | System tray |
| `systray_ignore` | array | `["blueman", "network"]` | Icons hidden from system tray |
| `control_center` | bool | `true` | Control center widget |
| `search` | bool | `true` | Search/spotlight button |
| `global_menu` | bool | `true` | App menus in panel |
| `network` | bool | `true` | Network indicator |
| `battery` | bool | `true` | Battery indicator |
| `bluetooth` | bool | `true` | Bluetooth indicator |
| `date_time` | bool | `true` | Date/time indicator |
| `workspace_indicator` | bool | `true` | Workspace indicator |
| `notification_center` | bool | `true` | Notification center |
| `notch` | bool | `true` | Center notch (player, indicators, recording) |
| `osd` | bool | `true` | Volume/brightness on-screen display |
| `night_light_temperature` | int | `4500` | Night light color temp in Kelvin |
| `hide_special_workspace` | bool | `true` | Hide special workspace from indicators |
| `custom_mods` | bool | `true` | Custom panel buttons from `mods.toml` |

### `[switcher]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `live_preview` | bool | `true` | Live window previews in switcher |
| `live_preview_delay_ms` | int | `200` | Preview framerate delay (lower = smoother) |
| `window_switcher` | bool | `true` | Alt-Tab window switcher |

### `[notification]`

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `timeout` | string | `"5s"` | Auto-dismiss duration |
| `ignored_apps` | array | `["Hyprshot"]` | Apps with suppressed notifications |
| `limited_apps_history` | array | `["Spotify"]` | Apps with limited history |

---

## Keybinds

Defined in `config/hypr/modus.lua`:

| Key | Action |
|-----|--------|
| `Super + D` | Spotlight search |
| `Super + E` | Emoji picker |
| `Super + V` | Clipboard history |
| `Super + W` | Wallpaper browser |
| `Super + I` | Settings window |
| `Super + L` | Lock screen |
| `Super + Z` | Screencapture toggle |
| `Super + S` | Screenshot region |
| `Alt + Tab` | Window switcher |
| `Alt + Space` | Keyboard layout switch |
| `Super + Shift + R` | Reload Modus |
| `Super + Shift + Y` | Reload CSS |
| `Alt + Shift + W` | Random wallpaper |

---

## `mods.toml` (Custom Panel Buttons)

Define custom buttons for the top panel. **Changes reload instantly!**

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

[Mods.power-menu]
icon = "power.svg"
icon-size = 18
order = 2
on-left = "wlogout"
```

**Properties:**
- `icon` — SVG filename in `src/assets/icons/`
- `icon-size` — defaults to 16
- `order` — left-to-right position (lower = first)
- `on-clicked`, `on-left`, `on-right`, `on-middle` — shell commands via `sh -c`
- `on-scroll-up`, `on-scroll-down` — scroll event commands
- `options` — dropdown menu entries (each with `label` + `on-clicked`)
  - Add `divider = true` before an option to insert a separator
- Full shell syntax (`&&`, `|`) supported

---

## `dock.toml` (Pinned Apps)

```toml
pinned = [
    "firefox",
    "kitty",
    "org.gnome.Nautilus"
]
```

Use the exact `.desktop` file name or application ID.

---

## Desktop Widgets (`config/desktop/` + `desktop.toml`)

Desktop widgets render directly on your wallpaper. Drop a `.py` file in `config/desktop/` and it appears live.

### Adding a Widget

```bash
cp examples/desktop/example.py config/desktop/example.py
```

The widget file calls `DesktopWidgetRegistry.register()` with a key, class, size, and default position:

```python
DesktopWidgetRegistry.register("my_widget", MyWidget, (174, 174), (0.5, 0.5))
```

### Positioning

Positions live in `config/desktop.toml`, one entry per monitor:

```toml
[[0]]
key = "my_widget"
px = 0.5
py = 0.5
```

- `0` = monitor ID
- `px`, `py` = 0.0–1.0 fractions of screen

Drag widgets in edit mode (right-click desktop → Edit Widgets) to reposition.

### Removing a Widget

Delete the `.py` file from `config/desktop/`:

```bash
rm config/desktop/example.py
```

Widget disappears within 2 seconds. The entry is also removed from `desktop.toml`.

### Built-in Widgets

| Key | Description |
|-----|-------------|
| `date` | Date display |
| `weather` | Weather info |
| `calendar` | Monthly calendar |
| `cpu_info` | CPU usage |
| `ram_info` | RAM usage |

See [Desktop Widgets Guide](desktop_widgets.md) for full documentation and examples.
