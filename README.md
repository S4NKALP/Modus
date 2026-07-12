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

## Links

| Doc | What's inside |
|-----|---------------|
| [Installation Guide](docs/installation.md) | Automated & manual install, dependencies |
| [Configuration Guide](docs/configuration.md) | `config.toml`, `mods.toml`, `dock.toml`, keybinds |
| [Styling Guide](docs/styling.md) | Matugen colors, CSS customization |
| [Architecture Overview](docs/architecture.md) | App Switcher C-backend, Spotlight engine, Services |
| [Spotlight Plugins](docs/plugins.md) | Install/customize plugins, write your own, examples |
| [FAQs & Tips](docs/faqs_tips.md) | Troubleshooting, shortcuts, live reload |
| [Contributing](CONTRIBUTING.md) | Setup, code style, commit conventions |

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
> - Check `config/hypr/modus.conf` edit it according to your device and copy it to your hyprland config
> - For Lock Screen Bind keys to `uv run lock`

## Spotlight Plugins

The spotlight search (Super+D) is powered by plugins. Drop a `.py` file in
`config/plugins/` and it works instantly.

```bash
cp -r examples/plugins/hello.py config/plugins/hello.py
# Hit Super+D, type "hi" — greeting appears
```

Plugin development:
```bash
vim config/plugins/hello.py
fabric-cli exec modus1 'deep_reload hello'   # no restart needed
```

See [Spotlight Plugins](docs/plugins.md) for full docs and examples.

## Configuration

Config files in `config/`, using TOML format:

| File | Purpose |
|------|---------|
| `config.toml` | Main settings (switcher, wallpaper, notifications) |
| `mods.toml` | Custom panel buttons |
| `dock.toml` | Pinned dock apps |

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

## Manual Installation

```bash
paru -S uv fabric-cli-git cliphist gnome-bluetooth-3.0 slurp ffmpeg hypridle hyprsunset hyprpicker hyprshot grim libnotify matugen-bin playerctl gtk-session-lock awww apple-fonts swappy wl-clipboard webp-pixbuf-loader wf-recorder acpi brightnessctl power-profiles-daemon uwsm cinnamon-desktop ddcutil at-spi2-core gcc make pkgconf appmenu-gtk-module libdbusmenu-gtk3 libdbusmenu-qt5 meson ninja wayland-protocols --needed
git clone https://github.com/S4NKALP/Modus ~/.config/Modus
cd ~/.config/Modus
uv sync

# Compile App Switcher C-backend
cd src/window/switcher/app-capture
meson setup builddir
meson compile -C builddir
cd ../../../..

# Compile Global Menu shim
cd src/globalmenu
gcc -shared -fPIC -O2 -o libmenu_button_shim.so libmenu_button_shim.c $(pkg-config --cflags --libs gtk+-3.0) -ldl
cd ../..

uv run start
```

## Roadmap

- [x] Spotlight
- [x] Lock Screen
- [x] Dock
- [x] Notification
- [x] Control Center
- [x] Music Player
- [x] Desktop Widgets
- [x] Spotlight
- [x] Settings
- [x] Magnifier hover effect on Dock
- [x] New Application Switcher (with high-performance Live Wayland Previews via custom C-backend)
- [x] Built-in Screen Capture & Screen Recording Widget
- [x] Panel Widget
- [x] MacOS like Widget
- [x] Expandable Notification Centre
- [x] Installation Script
- [x] Migrate to a `uv` managed Python virtual environment
- [x] To-do List Widget
- [x] Proper Documentation
- [x] Pomodoro Timer Widget

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
