# Installation Guide

Modus is a hackable shell for Hyprland built with Fabric. There are two primary ways to install it on Arch Linux.

## Automated Installation (Recommended)

> [!IMPORTANT]
> You need a working installation of Hyprland and knowledge of how it works. Ensure you are running this as a regular user (not root).

1. **Clone the Repository:**
   ```bash
   git clone https://github.com/S4NKALP/Modus ~/.config/Modus
   cd ~/.config/Modus
   ```

2. **Run the Installer Script:**
   ```bash
   ./install.sh
   ```
   The interactive installer will check requirements, install missing dependencies via `paru`/`yay`, build the necessary C-extensions (like `libappcapture.so` and `libmenu_button_shim.so`), and configure your Hyprland environment automatically.

## Manual Installation

If you prefer to install dependencies and compile the extensions manually:

1. **Install Dependencies:**
   ```bash
   paru -S uv fabric-cli-git cliphist gnome-bluetooth-3.0 slurp ffmpeg hypridle hyprsunset hyprpicker hyprshot grim libnotify matugen-bin playerctl gtk-session-lock awww apple-fonts swappy wl-clipboard webp-pixbuf-loader wf-recorder acpi brightnessctl power-profiles-daemon uwsm cinnamon-desktop ddcutil at-spi2-core gcc make pkgconf appmenu-gtk-module libdbusmenu-gtk3 libdbusmenu-qt5 meson ninja wayland-protocols --needed
   ```

2. **Clone and Sync:**
   ```bash
   git clone https://github.com/S4NKALP/Modus ~/.config/Modus
   cd ~/.config/Modus
   uv sync
   ```

3. **Compile the App Switcher C-Backend:**
   ```bash
   cd src/window/switcher/app-capture
   meson setup builddir
   meson compile -C builddir
   cd ../../../..
   ```

4. **Compile the Global Menu Shim:**
   ```bash
   cd src/globalmenu
   gcc -shared -fPIC -O2 -o libmenu_button_shim.so libmenu_button_shim.c $(pkg-config --cflags --libs gtk+-3.0) -ldl
   cd ../..
   ```

5. **Start Modus:**
   ```bash
   uv run start
   ```

> [!TIP]
> ### Post-Installation Recommendations
> - Install the recommended icon theme: [MacTahoe-icon-theme](https://github.com/vinceliuice/MacTahoe-icon-theme)
> - Install the recommended GTK theme: [MacTahoe-gtk-theme](https://github.com/vinceliuice/MacTahoe-gtk-theme)
> - Edit your Hyprland configuration file to source `~/.config/Modus/config/hypr/modus.conf` for the best compatibility.
