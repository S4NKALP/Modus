# Modus Documentation

Welcome to the official documentation for Modus! 

Modus is a highly customizable, hackable shell environment designed specifically for Hyprland on Wayland, built using Python and the [Fabric](https://github.com/Fabric-Development/fabric/) framework.

## Table of Contents

1. **[Installation Guide](installation.md)**
   - Automated installation via `install.sh`.
   - Manual installation and compiling C-extensions.
   - Post-installation steps and recommended themes.

2. **[Configuration Guide](configuration.md)**
   - How to configure the shell using `config.toml`.
   - Setting up custom panel buttons with `mods.toml`.
   - Pinning apps to the dock via `dock.toml`.

3. **[Styling Guide](styling.md)**
   - How Matugen dynamically generates colors based on your wallpaper.
   - Customizing CSS components in `src/shared/styles/`.

4. **[Architecture Overview](architecture.md)**
   - Deep dive into how Modus is built.
   - The Wayland Window Switcher C-Backend (`AppCapture`).
   - The Global Menu DBus implementation.

5. **[FAQs & Tips](faqs_tips.md)**
   - Troubleshooting common issues (Dock occlusion, CPU usage, OSD).
   - Pro tips for keyboard shortcuts and live-reloading.

---

## Contributing

Modus is open-source and hackable by design. If you want to contribute to the project:
1. Familiarize yourself with the [Architecture Overview](architecture.md).
2. Write Python code using the Fabric framework widgets.
3. Ensure you test your changes by running `uv run start` before opening a pull request.
