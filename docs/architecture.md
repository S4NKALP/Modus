# Architecture Overview

Modus is built using **Python** and the **Fabric** framework (a GTK/Wayland wrapper), along with custom C extensions for high-performance Wayland interactions.

## 1. Core Application Loop

The entry point of Modus is `start.py`, which delegates to `src/main.py`. 
`main.py` instantiates the `fabric.Application` object. This central application manages the lifecycle of various floating Wayland windows (called "widgets" or "panels" in Modus).

Key windows include:
- **Panel**: The top bar (`src/window/panel/`)
- **Dock**: The macOS-style bottom dock (`src/window/dock/`)
- **Control Center**: The right-side quick settings panel (`src/window/controlcenter/`)
- **App Switcher**: The Alt-Tab window switcher (`src/window/switcher/`)
- **Lock Screen**: The session lock screen (`src/window/lock.py`)

## 2. High-Performance App Switcher (AppCapture)

The App Switcher (`Alt+Tab`) needs to display live video previews of running Wayland windows. Doing this in pure Python via DBus polling would be far too slow and resource-intensive.

To solve this, Modus uses a custom C-extension located in `src/window/switcher/app-capture/`.
- **How it works**: It uses the `hyprland-toplevel-export-v1` Wayland protocol to ask Hyprland for direct memory-mapped buffers (dmabuf/shm) of the window contents.
- **Python Integration**: The C-backend is compiled to `libappcapture.so` and exposed to Python via GObject Introspection.
- **Optimization**: To prevent CPU spikes when capturing 4K windows, the capture framerate is intentionally throttled by Python using `invoke_repeater`, controlled by `switcher_live_preview_delay_ms` in `config.toml`.

## 3. Global Menu (DBus)

Modus features a macOS-style Global Menu (the application menu bar sits in the top panel instead of inside the app window).

- **How it works**: Apps export their menus over the `com.canonical.dbusmenu` DBus interface.
- **The Shim**: To force GTK apps to export their menus even if they weren't natively designed to, Modus preloads a custom C library (`src/globalmenu/libmenu_button_shim.c`). This shim hooks into GTK's menu generation and forces the export.
- **Python Daemon**: The Python side (`src/globalmenu/service.py`) acts as a DBus server, listens for these exported menus, and dynamically renders them as Fabric widgets in the top panel.

## 4. State Management & Services

Modus relies heavily on asynchronous event-driven services located in `src/services/`.
These services monitor system states and emit signals when things change, updating the UI reactively:
- `battery.py`: Uses UPower over DBus to track battery state.
- `bluetooth.py`: Uses BlueZ over DBus.
- `brightness.py`: Uses `brightnessctl` or `ddcutil`.
- `network.py`: Uses NetworkManager over DBus.

By using signals (`connect("changed", update_ui)`), Modus ensures that it uses virtually 0% CPU while idle.
