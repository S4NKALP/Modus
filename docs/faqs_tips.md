# FAQs & Tips

## Frequently Asked Questions

### 1. The Global Menu isn't showing up for some apps?

Modus uses a custom `libmenu_button_shim.so` with `appmenu-gtk-module` to
export GTK menus over DBus.
- Ensure `appmenu-gtk-module` is installed
- Ensure the shim was compiled correctly during installation
- Non-GTK apps (Electron, Qt) may need flags like
  `export QT_QPA_PLATFORMTHEME=appmenu-qt5`

### 2. High CPU usage when App Switcher is open?

The App Switcher uses a custom C-backend to capture live window previews.
- 4K windows with many open can spike CPU
- **Fix**: Increase `switcher.live_preview_delay_ms` in `config.toml` (e.g., `200`
  for ~5 FPS) or set `switcher.live_preview = false` to disable previews entirely

### 3. Dock covering fullscreen games/videos?

Set `dock.auto_hide = true` in `config.toml`. The dock hides automatically
when a window is maximized or fullscreen.

### 4. Volume/Brightness OSD not showing?

Set `panel.osd = true` in `config.toml`. Requires `brightnessctl` for brightness and
Pipewire/Wireplumber for audio.

### 5. Weather widget shows wrong location?

Update `general.weather_location` in `config.toml` (e.g., `"London, UK"` or
`"Patan, Nepal"`).

### 6. Spotlight plugin isn't showing up?

- Check the file is in `config/plugins/` (not `examples/plugins/`)
- Check `config/plugins/` is NOT in `.gitignore` for your own repos
- Run `journalctl --user -f -t modus` and look for `[PluginLoader]` errors
- Make sure the file has `PLUGIN = YourClassName` at the bottom
- If using dependencies, ensure `uv` is installed
- After editing, run `fabric-cli exec modus1 'deep_reload your_plugin_id'`

### 7. Plugin has dependencies but they aren't installed?

- Check `uv` is installed (`which uv`)
- Check `requirements.txt` is next to your `.py` file or inside your package dir
- The venv lives at `config/plugins/.venvs/<plugin_name>/`
- Delete that directory to force re-install on next load

### 8. Desktop widget not appearing?

- Check the file is in `config/desktop/` (not a subdirectory)
- Ensure it calls `DesktopWidgetRegistry.register()` at module level
- Check `journalctl --user -f -t modus` for `[DesktopWidgets]` errors
- Ensure the widget `key` is unique (not `"date"`, `"weather"`, etc.)

### 9. Desktop widget still showing after deleting the file?

The cleanup runs within 2 seconds via file monitor + poll fallback. If it persists:
- Check `journalctl --user -f -t modus` for stale widget messages
- Restart Modus: `uv run start`

### 10. Desktop widget position resets after restart?

- Positions are stored in `config/desktop.toml`
- If you delete `desktop.toml`, positions revert to defaults from `register()` calls
- Ensure `config/desktop.toml` is writable

### 11. Desktop widget interfering with window keybinds (e.g., Super+Q)?

The desktop window is a full-screen layer shell surface, which can intercept pointer events and make Hyprland treat it as the focused window. Modus handles this by using a **partial input region** — only widget areas receive input; empty desktop space passes through.

If keybinds still don't work:
- Check the widget's `size` in `register()` matches its actual rendered size
- Ensure no widget is expanding beyond its expected bounds (e.g., `h_expand=True` without fixed width)
- Restart Modus: `uv run start`

---

## Pro Tips

- **Live Reload for Mods**: `config/mods.toml` is monitored for changes. Edits
  apply instantly — no restart needed

- **Desktop Widgets**: Drop `.py` files in `config/desktop/` for instant widgets.
  Edit `config/desktop.toml` or drag in edit mode to reposition.
  Remove by deleting the `.py` file — disappears within 2 seconds.

- **Pinning Apps**: Use exact `.desktop` filename in `dock.toml` (e.g.,
  `"org.gnome.Nautilus"`, not `"Files"`)

- **Custom Scripts**: `on-clicked` in `mods.toml` can point to bash scripts in
  your home directory

- **Theme Updates**: Modus uses Matugen tied to your wallpaper. Set a new
  wallpaper and the shell recolors automatically

- **Keyboard Shortcuts** (from `config/hypr/modus.lua`):

  | Key | Action |
  |-----|--------|
  | `Super + D` | Open spotlight search |
  | `Super + E` | Open emoji picker |
  | `Super + V` | Open clipboard history |
  | `Super + W` | Open wallpaper browser |
  | `Super + I` | Open settings |
  | `Super + L` | Lock screen |
  | `Super + Z` | Screencapture toggle |
  | `Super + S` | Screenshot region |
  | `Alt + Tab` | Window switcher |
  | `Alt + Shift + W` | Random wallpaper |

- **Deep Reload a Plugin**: After editing `config/plugins/hello.py`:

  ```bash
  fabric-cli exec modus1 'deep_reload hello'
  ```

  No Modus restart required. Works with all plugins.

- **Test a Plugin from Terminal**:

  ```bash
  fabric-cli exec modus1 'wth london'
  ```

  Routes to the weather plugin's `search()` and prints results to the Modus log.

- **Check Plugin Load Log**:

  ```bash
  journalctl --user -f -t modus
  ```

  Filters to Modus messages only. Shows plugin discovery, load errors, and
  search crashes.

- **Screencapture Shortcuts** (from `config/hypr/modus.lua`):

  | Key | Action |
  |-----|--------|
  | `Super + Z` | Toggle screencapture |
  | `Super + S` | Screenshot region |
