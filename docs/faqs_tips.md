# FAQs & Tips

## Frequently Asked Questions

### 1. The Global Menu isn't showing up for some apps?
Modus uses a custom `libmenu_button_shim.so` along with `appmenu-gtk-module` to export GTK menus over DBus.
- Ensure `appmenu-gtk-module` is installed.
- Ensure the shim was compiled correctly during installation.
- Note that non-GTK apps (like Electron apps or Qt apps) might need specific flags (like `export QT_QPA_PLATFORMTHEME=appmenu-qt5`) to export their menus.

### 2. High CPU Usage when the Application Switcher is open?
The Modus App Switcher uses a custom Wayland C-Backend (`app-capture`) to generate live video previews of your running windows.
- The previews are software-rendered via Cairo.
- If you have many 4k windows open, generating live thumbnails might cause a CPU spike.
- **Fix:** You can throttle the framerate in `config.toml` by increasing `switcher_live_preview_delay_ms` (e.g., set to `200` for ~5 FPS), or entirely disable live previews by setting `switcher_live_preview = false`.

### 3. The Dock is covering my fullscreen games/videos?
Ensure you have `dock_auto_hide = true` in your `config.toml`. The dock intelligently hides when a window is maximized or goes fullscreen.

### 4. Why isn't my Volume or Brightness OSD showing up?
Ensure that `osd = true` is set in your `config.toml`. The On-Screen Display relies on `brightnessctl` for brightness and standard audio services (like Pipewire/Wireplumber) for volume. Make sure those underlying tools are working correctly on your system.

### 5. The Weather widget is showing the wrong location?
You can easily fix this by updating the `weather_location` setting in your `config.toml`. Simply type your city and country (e.g., `"London, UK"` or `"Patan, Nepal"`), and the widget will fetch the correct local weather.

---

## Pro Tips

- **Live Reload for Mods:** The `config/mods.toml` file is actively monitored. Any changes you make to custom panel buttons or dropdown menus are instantly loaded—no shell restart required!
- **Pinning Apps Correctly:** When pinning apps in `dock.toml`, ensure you use the exact `.desktop` file name (excluding the `.desktop` extension). For example, use `"org.gnome.Nautilus"` instead of just `"nautilus"` or `"Files"`.
- **Custom Scripts in Panel:** You aren't limited to simple commands in `mods.toml`. You can point the `on-clicked` actions to complex bash scripts stored in your home directory to create advanced panel utilities.
- **Forcing a Theme Update:** Because Modus uses Matugen for styling, the entire shell's color scheme is tethered to your wallpaper. If you want to completely change the look of your desktop, simply set a new wallpaper! Modus will automatically generate a new palette and hot-reload the UI without dropping your session.
- **Keyboard Shortcuts:**
  - `uv run start` — Starts the main shell daemon.
  - `uv run lock` — Triggers the session lock screen.
- **Wayland Screencapture:** You can quickly toggle the screen recording/capture widget from the panel or bind it to a key using your Hyprland config (e.g. `bind = SUPER, S, exec, fabric-cli exec modus 'screencapture.toggle()'`).
