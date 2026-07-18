# Contributing to Modus

Thanks for your interest in contributing to Modus! This guide covers everything you need to get started.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Setup](#setup)
- [Project Structure](#project-structure)
- [Development Workflow](#development-workflow)
- [Code Style](#code-style)
- [Commit Messages](#commit-messages)
- [Pull Requests](#pull-requests)
- [Reporting Bugs](#reporting-bugs)
- [Requesting Features](#requesting-features)

## Prerequisites

- Arch Linux with [Hyprland](https://hyprland.org/) (Wayland compositor)
- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- [Meson](https://mesonbuild.com/) + Ninja (for C backends)
- GCC (for Global Menu shim)

Install all dependencies:

```bash
paru -S uv fabric-cli-git cliphist gnome-bluetooth-3.0 slurp ffmpeg hypridle hyprsunset hyprpicker hyprshot grim libnotify matugen-bin playerctl gtk-session-lock awww apple-fonts swappy wl-clipboard webp-pixbuf-loader wf-recorder acpi brightnessctl power-profiles-daemon uwsm cinnamon-desktop ddcutil at-spi2-core gcc make pkgconf appmenu-gtk-module libdbusmenu-gtk3 libdbusmenu-qt5 meson ninja wayland-protocols --needed
```

## Setup

```bash
# Fork and clone
git clone https://github.com/<your-username>/Modus.git ~/.config/Modus
cd ~/.config/Modus

# Install dependencies
uv sync

# Compile App Switcher C backend
cd src/window/switcher/app-capture
meson setup builddir
meson compile -C builddir
cd ../../../..

# Compile Global Menu shim
cd src/window/globalmenu
gcc -shared -fPIC -O2 -o libmenu_button_shim.so libmenu_button_shim.c $(pkg-config --cflags --libs gtk+-3.0) -ldl
cd ../../..

# Run
uv run start
```

## Project Structure

```
Modus/
├── src/
│   ├── main.py                    # App bootstrap
│   ├── services/                  # System service monitors (DBus, signals)
│   ├── shared/                    # Reusable widgets and base window classes
│   ├── utils/                     # Utility modules
│   ├── window/                    # All UI windows
│   │   ├── panel/                 # Top bar
│   │   ├── dock/                  # macOS-style dock
│   │   ├── controlcenter/         # Quick settings panel
│   │   ├── notification/          # Notification system
│   │   ├── switcher/              # Alt-Tab app switcher (C backend)
│   │   ├── spotlight/             # Super+D search (plugin system)
│   │   ├── osd/                   # Volume/brightness on-screen display
│   │   ├── screencapture/         # Screen capture/recording
│   │   ├── desktop/               # Desktop widgets
│   │   ├── settings/              # Settings window
│   │   ├── globalmenu/            # macOS global menu bar
│   │   └── lock.py                # Session lock screen
│   └── styles/                    # GTK CSS stylesheets
├── config/                        # User-facing config (TOML)
│   ├── config.toml                # Main settings
│   ├── mods.toml                  # Custom panel buttons
│   ├── dock.toml                  # Pinned dock apps
│   └── plugins/                   # User-installed spotlight plugins
├── examples/                      # Example plugins
├── docs/                          # Documentation
├── pyproject.toml                 # Project config + Ruff linting
└── start.py                       # Entry point
```

## Development Workflow

1. **Create a branch** from `dev`:
   ```bash
   git checkout dev
   git checkout -b feat/my-feature
   ```

2. **Make your changes** and ensure they pass linting:
   ```bash
   # Lint
   .venv/bin/ruff check

   # Auto-fix lint issues
   .venv/bin/ruff check --fix

   # Format
   .venv/bin/ruff format

   # Check formatting without changing files
   .venv/bin/ruff format --check
   ```

3. **Test your changes** by running the app:
   ```bash
   uv run start
   ```

4. **Commit** with a descriptive message (see [Commit Messages](#commit-messages)).

5. **Push** and open a Pull Request against `dev`.

## Code Style

Modus uses [Ruff](https://docs.astral.sh/ruff/) for both linting and formatting. The full config is in `pyproject.toml`.

### Key Rules

- **Formatter**: Double quotes, 4-space indentation, 88 char line length
- **Import sorting**: Grouped as stdlib / third-party / first-party, alphabetical within groups
- **Type hints**: Use `Optional[X]` and `typing.List`, `typing.Dict` style (not PEP 604 unions)
- **Logging**: Use `logger` from `fabric.utils`, not `print()` (except in CLI entry points)
- **Docstrings**: Not enforced, but encouraged for public APIs

### Enforced via Ruff

| Rule | What it catches |
|------|----------------|
| `E`, `W` | Pycodestyle style errors |
| `F` | Pyflakes (unused imports, undefined names) |
| `I` | Import sorting (isort) |
| `UP` | Python upgrade suggestions |
| `B` | Bugbear (common bugs) |
| `SIM` | Simplification suggestions |
| `C4` | Unnecessary comprehensions |
| `RET` | Return statement issues |
| `RUF` | Ruff-specific rules |
| `T20` | `print()` detection |

### Running Ruff

```bash
# Check for issues
.venv/bin/ruff check

# Auto-fix safe issues
.venv/bin/ruff check --fix

# Auto-fix including unsafe changes
.venv/bin/ruff check --fix --unsafe-fixes

# Format all files
.venv/bin/ruff format

# Check formatting (CI-friendly)
.venv/bin/ruff format --check
```

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <summary>
```

### Types

| Type | Use for |
|------|---------|
| `feat` | New feature |
| `fix` | Bug fix |
| `refactor` | Code restructuring without behavior change |
| `perf` | Performance improvement |
| `docs` | Documentation changes |
| `style` | Code style changes (formatting, no logic change) |
| `chore` | Build, CI, tooling, dependencies |
| `test` | Adding or updating tests |

### Scopes

Use the module name: `services`, `window`, `dock`, `panel`, `spotlight`, `notification`, `switcher`, `osd`, `config`, `docs`, etc.

### Examples

```
feat(dock): add magnifier hover effect
fix(notification): prevent crash on empty body
refactor(services): extract battery polling to separate thread
docs: update installation guide for Arch Linux
style: enforce consistent codestyle via ruff config
```

### Rules

- Use imperative mood: "add" not "added" or "adds"
- Keep subject line under 72 characters
- Reference issues when applicable: `Closes #42`
- Body is optional — use it only to explain **why**, not **what**

## Pull Requests

### Before Submitting

- [ ] Code passes `ruff check` with no errors
- [ ] Code passes `ruff format --check`
- [ ] Changes are tested on a live Hyprland session
- [ ] Commit messages follow [Conventional Commits](#commit-messages)

### PR Guidelines

- Target the `dev` branch (not `main`)
- Keep PRs focused — one feature or fix per PR
- Write a clear description of what changed and why
- Include screenshots or screen recordings for UI changes
- Reference related issues

## Reporting Bugs

Open an issue with:

1. **Description**: What happened vs. what you expected
2. **Steps to reproduce**: Exact commands or actions
3. **Environment**: OS, Hyprland version, Python version
4. **Logs**: Relevant output from terminal or journal

## Requesting Features

Open an issue with:

1. **Use case**: What problem does this solve?
2. **Proposed solution**: How should it work?
3. **Alternatives considered**: Other approaches you thought about
