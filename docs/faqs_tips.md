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
- **Fix**: Increase `switcher_live_preview_delay_ms` in `config.toml` (e.g., `200`
  for ~5 FPS) or set `switcher_live_preview = false` to disable previews entirely

### 3. Dock covering fullscreen games/videos?

Set `dock_auto_hide = true` in `config.toml`. The dock hides automatically
when a window is maximized or fullscreen.

### 4. Volume/Brightness OSD not showing?

Set `osd = true` in `config.toml`. Requires `brightnessctl` for brightness and
Pipewire/Wireplumber for audio.

### 5. Weather widget shows wrong location?

Update `weather_location` in `config.toml` (e.g., `"London, UK"` or
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

---

## Pro Tips

- **Live Reload for Mods**: `config/mods.toml` is monitored for changes. Edits
  apply instantly — no restart needed

- **Pinning Apps**: Use exact `.desktop` filename in `dock.toml` (e.g.,
  `"org.gnome.Nautilus"`, not `"Files"`)

- **Custom Scripts**: `on-clicked` in `mods.toml` can point to bash scripts in
  your home directory

- **Theme Updates**: Modus uses Matugen tied to your wallpaper. Set a new
  wallpaper and the shell recolors automatically

- **Spotlight Keyboard Shortcuts** (from `config/hypr/modus.lua`):

  | Key | Action |
  |-----|--------|
  | `Super + D` | Open spotlight search |
  | `Super + E` | Open emoji picker |
  | `Super + V` | Open clipboard history |
  | `Super + W` | Open wallpaper browser |
  | `Alt + Shift + W` | Set random wallpaper |

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
