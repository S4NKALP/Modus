<p align="center">
  <img src="src/assets/modus.png" height="200" alt="Logo">
</p>

<p align="center">
  <sub><sup><img src="https://raw.githubusercontent.com/Tarikul-Islam-Anik/Telegram-Animated-Emojis/main/Activity/Sparkles.webp" alt="Sparkles" width="25" height="25"/></sup></sub>
  <a href="https://github.com/hyprwm/Hyprland">
    <img src="https://img.shields.io/badge/A%20hackable%20shell%20for-Hyprland-0092CD?style=for-the-badge&logo=linux&color=0092CD&logoColor=D9E0EE&labelColor=000000" alt="A hackable shell for Hyprland">
  </a>
  <a href="https://github.com/Fabric-Development/fabric/">
    <img src="https://img.shields.io/badge/Powered%20by-Fabric-FAFAFA?style=for-the-badge&logo=python&color=FAFAFA&logoColor=D9E0EE&labelColor=000000" alt="Powered by Fabric">
  <sub><sup><img src="https://raw.githubusercontent.com/Tarikul-Islam-Anik/Telegram-Animated-Emojis/main/Activity/Sparkles.webp" alt="Sparkles" width="25" height="25"/></sup></sub>
  </a>
  </p>

<div align="center">

[![GitHub stars](https://img.shields.io/github/stars/S4NKALP/Modus?style=for-the-badge&logo=github&color=FFB686&logoColor=D9E0EE&labelColor=292324)](https://github.com/S4NKALP/Modus/stargazers)
[![Hyprland](https://img.shields.io/badge/Made%20for-Hyprland-pink?style=for-the-badge&logo=linux&logoColor=D9E0EE&labelColor=292324&color=C6A0F6)](https://hyprland.org/)
[![Maintained](https://img.shields.io/badge/Maintained-Yes-blue?style=for-the-badge&logo=linux&logoColor=D9E0EE&labelColor=292324&color=3362E1)]()
[![Discord](https://dcbadge.limes.pink/api/server/https://discord.gg/tRFxkbQ3Zq)](https://discord.gg/tRFxkbQ3Zq)

</div>

<br>

<figure>
  <h2>Home Screen:</h2>
  <img src="src/assets/screenshots/home.png" alt="fabric">
  <br/>
  <h2>Lock Screen:</h2>
    <img src="src/assets/screenshots/lock.png" alt="fabric">
</figure>
<br>

## Quick Start

```bash
git clone https://github.com/S4NKALP/Modus ~/.config/Modus
cd ~/.config/Modus
./install.sh
```

> [!TIP]
>
> ## Post Installation
>
> - Install recommended [Icon theme](https://github.com/vinceliuice/MacTahoe-icon-theme) , [GTK theme](https://github.com/vinceliuice/MacTahoe-gtk-theme) and [Cursor Theme](https://github.com/vinceliuice/MacTahoe-icon-theme/tree/main/cursors) <br>
> - Check `config/hypr/modus.lua` edit it according to your device and copy it to your hyprland config
> - For Lock Screen Bind keys to `uv run lock`

## Manual Installation

```bash
paru -S uv fabric-cli-git uwsm cliphist slurp grim swappy wl-clipboard wtype libnotify playerctl matugen-bin hypridle hyprsunset hyprpicker hyprshot gtk-session-lock awww apple-fonts webp-pixbuf-loader cinnamon-desktop libmediaart acpi brightnessctl power-profiles-daemon ddcutil at-spi2-core networkmanager network-manager-applet blueman pipewire libpulse gcc make pkgconf meson ninja wayland-protocols gobject-introspection gtk-layer-shell librsvg libqalculate appmenu-gtk-module libdbusmenu-gtk3 libdbusmenu-qt5 pciutils wf-recorder ffmpeg --needed
git clone https://github.com/S4NKALP/Modus ~/.config/Modus
cd ~/.config/Modus
uv sync

# Compile App Switcher C-backend
cd src/window/switcher/app-capture
meson setup builddir
meson compile -C builddir
cd ../../../..

# Compile Global Menu shim
cd src/window/globalmenu
gcc -shared -fPIC -O2 -o libmenu_button_shim.so libmenu_button_shim.c $(pkg-config --cflags --libs gtk+-3.0) -ldl
cd ../../..

uv run start
```

## Global Menu Compatibility

MODUS injects the GTK3 menu-button shim (`libmenu_button_shim.so`) **only into
GTK3 apps**, and only when launched through MODUS (dock, spotlight, panel).
GTK4 apps are never touched, so they launch normally — a global `LD_PRELOAD`
of this shim would otherwise crash every GTK4 process.

### Terminal-launched GTK3 apps

Apps you start directly from a terminal don't go through MODUS, so they don't
get the shim. They still work fine; they just miss the synthetic
button-release fix the shim provides. To get it back without a dangerous
system-wide `LD_PRELOAD`, use a thin wrapper that detects GTK3 and injects the
shim only for that process:

```bash
#!/usr/bin/env bash
# ~/.local/bin/modus-launch — GTK3-aware launcher for the global menu shim
SHIM=~/.config/Modus/src/window/globalmenu/libmenu_button_shim.so
BIN="$(command -v "$1")"
if [[ -n "$BIN" ]] && readelf -d "$BIN" 2>/dev/null | grep -q 'libgtk-3\.so\.0'; then
    LD_PRELOAD="$SHIM" "$@"
else
    "$@"
fi
```

Make it executable (`chmod +x ~/.local/bin/modus-launch`) and run GTK3 apps as
`modus-launch gedit` from the terminal. GTK4 apps fall through to a normal
launch.

## Documentation

| Doc                                           | What's inside                                       |
| --------------------------------------------- | --------------------------------------------------- |
| [Installation Guide](docs/installation.md)    | Automated & manual install, dependencies            |
| [Configuration Guide](docs/configuration.md)  | `config.toml`, `mods.toml`, `dock.toml`, keybinds   |
| [Styling Guide](docs/styling.md)              | Matugen colors, CSS customization                   |
| [Architecture Overview](docs/architecture.md) | App Switcher C-backend, Spotlight engine, Services  |
| [Spotlight Plugins](docs/plugins.md)          | Install/customize plugins, write your own, examples |
| [FAQs & Tips](docs/faqs_tips.md)              | Troubleshooting, shortcuts, live reload             |
| [Contributing](CONTRIBUTING.md)               | Setup, code style, commit conventions               |

## Configuration

Config files in `config/`, using TOML format:

| File          | Purpose                                            |
| ------------- | -------------------------------------------------- |
| `config.toml` | Main settings (switcher, wallpaper, notifications) |
| `mods.toml`   | Custom panel buttons                               |
| `dock.toml`   | Pinned dock apps                                   |

See [Configuration Guide](docs/configuration.md) for full reference.

## Custom Mods

Define panel buttons in `config/mods.toml`:

```toml
[Mods.terminal]
icon = "terminal.svg"
icon-size = 16
order = 1
on-clicked = "kitty"
```

- `icon` — SVG filename in `src/assets/icons/`
- `icon-size` — defaults to 16
- `order` — button position (lower = first)
- `on-clicked` — shell command on click
- `on-left`, `on-middle`, `on-right` — per-mouse-button commands
- `options` — dropdown menu entries (each with `label` + `on-clicked`)
- Full shell syntax (`&&`, `|`) via `sh -c`
- Live reload — edit and changes apply instantly

## Spotlight Plugins

The spotlight search (Super+D) is powered by plugins. Drop a `.py` file in
`config/plugins/` and it works instantly.

```bash
cp -r examples/plugins/hello.py config/plugins/hello.py
# Hit Super+D, type "hi" — greeting appears
```

Plugin development:

```bash
nvim config/plugins/hello.py
fabric-cli exec modus1 'deep_reload hello'   # no restart needed
```

See [Spotlight Plugins](docs/plugins.md) for full docs and examples.

## Team

- [SANKALP](https://github.com/S4NKALP/)
- [tr1x_em](https://github.com/tr1xem)

## Special Thanks

A big thank you to the following people for their incredible help with code and creative ideas. Your help made a real difference!

- [darsh](https://github.com/its-darsh): for creating Fabric, which made everything possible.
- [gummy bear album](https://github.com/muhchaudhary): for sharing fantastic code snippets that saved me time and effort.
- [axenide](https://github.com/Axenide): for the amazing config that not only inspired parts of mine but also provided some gems I couldn't resist borrowing.
- [E3nviction](https://github.com/E3nviction/): for code snippets and ideas that were incredibly helpful.

I truly appreciate your support
