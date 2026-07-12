# Plugin Development Guide

Modus spotlight supports third-party plugins. Drop a Python file in `config/plugins/` and it gets auto-discovered on next startup.

## Quick Start

Copy the hello example to your plugins directory:

```bash
cp -r examples/plugins/hello.py config/plugins/hello.py
```

Open spotlight and type `hi` or `hello`. The plugin shows a greeting result.

## How It Works

## How It Works

1. On startup, Modus scans `config/plugins/` for `.py` files and package directories.
2. Each file is imported. The `PLUGIN` module-level variable is extracted (must be a `SpotlightPlugin` subclass).
3. Plugins are instantiated, initialized, and registered.
4. User types query -> spotlight routes to matching plugin (by keyword or global search) -> `search()` is called -> results are rendered.

## Plugin Class Attributes

| Attribute        | Type       | Required | Description |
|-----------------|------------|----------|-------------|
| `id`            | `str`      | Yes      | Unique identifier (e.g., `"weather"`). |
| `name`          | `str`      | Yes      | Human-readable name shown in UI. |
| `icon`          | `str`      | No       | GTK icon name for the header. |
| `keywords`      | `list[str]`| No       | Trigger prefixes (e.g., `["wall", "wr"]`). User types `wall <query>` to activate. |
| `searchable`    | `bool`     | No       | If `True`, plugin appears in global search (no prefix needed). Default `False`. |
| `priority`      | `int`      | No       | Lower = searched first in global results. Default `100`. |
| `refresh_interval` | `int`  | No       | Auto-refresh timer in ms (0 = disabled). Fires `on_timer_tick()`. |

## Methods

### Required

```python
def search(self, query: str, token: Any) -> list[SearchResult]:
    """Return results matching query.

    token: Cancellation token. Check token.is_cancelled before expensive work.
    Must return list of SearchResult. Never create GTK widgets.
    """
```

### Optional

| Method | When Called | Use Case |
|--------|-------------|----------|
| `initialize()` | After instantiation | Load data, start services |
| `cleanup()` | On unload/disable | Free resources |
| `reload()` | On refresh | Default: cleanup + initialize |
| `on_activate(update_fn)` | Keyword prefix matched | Set up state for keyword mode |
| `on_deactivate()` | Keyword prefix cleared | Tear down keyword state |
| `on_submit(query)` | Enter pressed in keyword mode | Handle final input |
| `detect(text)` | Global search, each keystroke | Return `True` to exclusively handle input |
| `handle_external(command, args)` | External command (e.g., keybind) | Handle non-search invocations |
| `release_memory()` | Spotlight hides | Clear heavy cached data |

## SearchResult Fields

```python
SearchResult(
    id="unique_id",           # Unique within your plugin
    title="Display Title",    # Main text
    subtitle="Description",   # Secondary text
    icon_name="",             # GTK icon name (optional)
    score=80.0,               # 0-100, higher = better match
    render_type="default",    # Controls rendering (see below)
    action=lambda: ...,       # Called when user selects this result
    plugin_name="",           # Auto-filled by spotlight
    plugin_id="",             # Auto-filled by spotlight
    metadata={},              # Arbitrary data for renderers
)
```

### Render Types

| `render_type`       | Widget Style                 | Use Case               |
|-------------------|-----------------------------|-----------------------|
| `"default"`       | Icon + title + subtitle      | Generic results       |
| `"app"`           | Desktop app icon + name      | Application spotlight |
| `"calc"`          | Expression + result          | Calculator            |
| `"emoji"`         | Emoji char + name + keywords | Emoji picker          |
| `"power"`         | Icon + name + description    | Power menu            |
| `"wallpaper"`     | Thumbnail image              | Wallpaper picker      |
| `"clipboard_text"`| Text preview                 | Clipboard entries     |
| `"clipboard_image"` | Image preview              | Clipboard images      |

Use `"default"` unless you need a specific layout. Custom render types can be added to `main.py`'s `_render_result()`.

## Keyword Plugins vs Global Search

**Keyword-only** (`searchable = False`):
- User types `gg <query>` -> routes exclusively to your plugin
- `search()` receives the text after the prefix (e.g., `"linux news"`)
- Good for: YouTube search, Google search, wallpaper browser

**Global search** (`searchable = True`):
- Plugin appears in results alongside apps, calculator, emoji
- `search()` receives the full query
- Good for: Calculator, emoji, power menu

**Both** (`searchable = True` + `keywords`):
- Activates via keyword prefix AND appears in global results
- Good for: Wallpapers, clipboard, weather

## Cancellation

The `token` parameter has an `is_cancelled` flag. Check it before expensive operations:

```python
def search(self, query: str, token: Any) -> list[SearchResult]:
    results = []
    for item in self._large_dataset:
        if token.is_cancelled:
            return []  # Abort immediately
        if self._matches(item, query):
            results.append(item)
    return results
```

The spotlight cancels previous searches when the user types new input. Without cancellation checks, your plugin wastes CPU on stale queries.

## Examples

### Hello World (single-file, no deps)

File: `config/plugins/hello.py`

```python
from typing import Any

from window.spotlight.api import SpotlightPlugin, SearchResult


class HelloPlugin(SpotlightPlugin):
    id = "hello"
    name = "Hello"
    icon = "face-smile-symbolic"
    keywords = ["hi", "hello"]
    searchable = True
    priority = 100

    def search(self, query: str, token: Any) -> list[SearchResult]:
        if not query.strip():
            return []
        return [
            SearchResult(
                id="hello_world",
                title="Hello, World!",
                subtitle="A friendly greeting",
                icon_name="face-smile-symbolic",
                score=100.0,
                render_type="default",
                action=lambda: print("Hello!"),
            )
        ]

PLUGIN = HelloPlugin
```

Test: `fabric-cli exec modus1 'deep_reload hello'`

### Google / YouTube / Link Opener (keyword-only, shell-safe)

File: `config/plugins/query.py` (built-in, but you can write your own)

```python
import urllib.parse
from typing import Any

from utils.functions import spawn_detached
from window.spotlight.api import SpotlightPlugin, SearchResult


class GooglePlugin(SpotlightPlugin):
    id = "google"
    name = "Google"
    icon = "system-search-symbolic"
    keywords = ["gg"]
    searchable = False

    def search(self, query: str, token: Any) -> list[SearchResult]:
        return []

    def on_submit(self, query: str) -> None:
        q = query.strip()
        if q:
            url = f"https://www.google.com/search?q={urllib.parse.quote(q)}"
            spawn_detached(["xdg-open", url])   # no shell injection risk


PLUGIN = GooglePlugin
```

Usage: type `gg linux news` then Enter. Opens browser.

### Weather Plugin (package plugin, third-party deps, I/O cancellation)

Full example on disk at `config/plugins/weather/`. Demonstrates:
- Package plugin structure
- Auto-installed dependencies via `requirements.txt` + `uv`
- I/O with cancellation checks
- Result caching

```python
"""Weather plugin for Modus spotlight.

Demonstrates:
  - Package plugin structure
  - Third-party deps via requirements.txt (uv venv auto-install)
  - Keyword activation + global search
  - Deep reload during development
  - Cancellation checks for I/O
  - External command support
"""

import os
from typing import Any

from window.spotlight.api import SpotlightPlugin, SearchResult

try:
    import requests
except ImportError:
    requests = None


class WeatherPlugin(SpotlightPlugin):
    id = "weather"
    name = "Weather"
    icon = "weather-clear-symbolic"
    keywords = ["wth", "weather"]
    searchable = True
    priority = 75

    def __init__(self, context):
        super().__init__(context)
        self._cache: dict | None = None

    def initialize(self) -> None:
        pass

    def cleanup(self) -> None:
        self._cache = None

    def search(self, query: str, token: Any) -> list[SearchResult]:
        q = query.strip().lower()

        # Strip keyword prefix ("wth london" -> "london")
        for prefix in ("wth ", "weather "):
            if q.startswith(prefix):
                q = q[len(prefix):].strip()
                break
        if q in ("wth", "weather"):
            q = ""

        if not q:
            return [SearchResult(...hint...)]

        data = self._fetch_weather(q, token)
        if token.is_cancelled or not data:
            return []

        temp = data.get("main", {}).get("temp", "?")
        desc = data.get("weather", [{}])[0].get("description", "?")
        city = data.get("name", q)

        return [
            SearchResult(
                id=f"weather_{q}",
                title=f"{city}: {temp}°C",
                subtitle=desc.capitalize(),
                icon_name="weather-clear-symbolic",
                score=100.0,
                render_type="default",
            )
        ]

    def _fetch_weather(self, city: str, token: Any) -> dict | None:
        """Fetch weather from OpenWeatherMap with caching."""
        if self._cache:
            return self._cache

        api_key = os.environ.get("OPENWEATHER_API_KEY")
        if not api_key or requests is None:
            return None

        resp = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"q": city, "appid": api_key, "units": "metric"},
            timeout=10,
        )
        if token.is_cancelled:
            return None
        if resp.status_code == 200:
            self._cache = resp.json()
            return self._cache
        return None

    def handle_external(self, command: str, args: str) -> None:
        print(f"External: {command} {args}")


PLUGIN = WeatherPlugin
```

File layout:

```
examples/plugins/weather/
  __init__.py          # plugin code
  requirements.txt     # requests>=2.28
```

Copy to plugins dir and try:
```bash
cp -r examples/plugins/weather config/plugins/weather
fabric-cli exec modus1 'deep_reload weather'
```

Now type `wth london` in spotlight.

On first load, `PluginLoader` creates `config/plugins/.venvs/weather/` via `uv venv`,
installs `requests` via `uv pip install`, then imports your plugin.

Usage: type `wth london` or just search `london` in global mode.

Set env var in your Hyprland config:
```
env = OPENWEATHER_API_KEY, your_key_here
```

### Color Picker (global search, clipboard action)

```python
from typing import Any

from utils.functions import run_command
from window.spotlight.api import SpotlightPlugin, SearchResult


class ColorPlugin(SpotlightPlugin):
    id = "colors"
    name = "Colors"
    icon = "color-select-symbolic"
    keywords = []
    searchable = True
    priority = 80

    COLORS = [
        ("Red", "#FF0000"),
        ("Green", "#00FF00"),
        ("Blue", "#0000FF"),
    ]

    def search(self, query: str, token: Any) -> list[SearchResult]:
        q = query.lower().strip()
        if not q:
            return []
        results = []
        for name, hex_code in self.COLORS:
            if q in name.lower():
                results.append(
                    SearchResult(
                        id=f"color_{name.lower()}",
                        title=name,
                        subtitle=hex_code,
                        icon_name="color-select-symbolic",
                        score=90.0,
                        render_type="default",
                        action=lambda h=hex_code: self._copy_color(h),
                    )
                )
        return results

    def _copy_color(self, hex_code: str) -> None:
        run_command(["wl-copy"], input=hex_code.encode(), text=False)


PLUGIN = ColorPlugin
```

## Package Plugins

For complex plugins, use a directory with `plugin.py` or `__init__.py`:

```
config/plugins/
  myplugin/
    __init__.py    # or plugin.py — must export PLUGIN = MyPluginClass
    utils.py
    data.json
    requirements.txt   # optional third-party deps
```

## Third-Party Dependencies

If your plugin needs external Python packages, add `requirements.txt` next to your plugin file or in your package directory. Modus auto-installs them into an isolated virtualenv using `uv`.

### Single-file plugin with dependencies

```
config/plugins/
  weather.py
  weather/requirements.txt   # companion directory
```

or

```
config/plugins/
  weather.py
  requirements.txt           # next to .py file
```

### Package plugin with dependencies

```
config/plugins/
  myplugin/
    __init__.py
    utils.py
    requirements.txt
```

### What happens at load time

1. Modus checks for `requirements.txt` next to your `.py` file or in your package directory.
2. If found, it creates a venv at `config/plugins/.venvs/<plugin_name>/` using `uv venv`.
3. It runs `uv pip install -r requirements.txt --python <venv>/bin/python`.
4. The venv's `site-packages` is added to `sys.path` before your plugin is imported.
5. If `requirements.txt` changes later, deps are re-installed automatically.
6. **Requirement**: `uv` must be installed (`pip install uv` or `cargo install uv`).

Only one `requirements.txt` per plugin is consulted. The venv persists across restarts.

## Development Workflow

### Edit → Reload → Test loop

The fastest way to develop a plugin:

1. Edit your plugin file
2. Run `fabric-cli exec modus1 'deep_reload your_plugin_id'`
3. Open spotlight and test

No Modus restart needed.

Example session:

```bash
# Copy the weather example
cp -r examples/plugins/weather config/plugins/weather

# --- First iteration ---
vim config/plugins/weather/__init__.py
fabric-cli exec modus1 'deep_reload weather'

# --- Watch logs ---
journalctl -f --user -t modus

# --- Second iteration ---
vim config/plugins/weather/__init__.py
fabric-cli exec modus1 'deep_reload weather'

# --- Test output from terminal ---
fabric-cli exec modus1 'wth london'
```

### Deep reload under the hood

```
fabric-cli exec modus1 'deep_reload weather'
```

1. `Spotlight.handle_external("deep_reload", "weather")` catches the built-in command
2. `PluginManager.deep_reload("weather")` runs:
   - `entry.instance.cleanup()` — free old resources
   - `PluginLoader.unload_module("modus_plugin_user_weather")` — removes stale module from `sys.modules`
   - `PluginLoader._load_package_plugin(path, "user")` — re-imports from disk
   - `entry.plugin_class = fresh_class` — swaps the class reference
   - `entry.instance = fresh_class(context)` — new instance
   - `entry.instance.initialize()` — fresh setup

### Check from terminal without UI

```bash
fabric-cli exec modus1 'your_plugin_id some_query'
```

This routes to the plugin via keyword match or direct id lookup.

### Errors & logging

If a plugin fails to load or crashes during search, check the Modus log:

```bash
journalctl --user -f -t modus
```

On reload failure, the old instance stays active. The log will show what went wrong.

## External Commands (Keybinds)

Plugins can be invoked from Hyprland keybinds via `handle_external`:

```python
def handle_external(self, command: str, args: str) -> None:
    if command == "myplugin":
        self._do_stuff(args)
```

Hyprland config:
```lua
["SUPER + M"] = "fabric-cli exec modus1 'myplugin some_argument'"
```

## Tips

- **Cache heavy data** in `initialize()`, not in `search()`. The search method runs on every keystroke.
- **Use `fuzzy_score`** from `utils.functions` for fuzzy matching against user input.
- **Keep `search()` fast**. If you do I/O, check `token.is_cancelled` frequently between operations.
- **Use `metadata`** to pass data to renderers. The spotlight owns all GTK widget creation — your plugin never touches widgets.
- **Use `run_command` from `utils.functions`** for subprocess calls — handles timeouts and errors. Never use shell strings (`exec_shell_command(f"...")`) with user input — that's a shell injection risk.
- **Use `spawn_detached` from `utils.functions`** to launch background processes without blocking.
- **Use `thread()` from `utils.functions`** for background work from `initialize()` or `handle_external()`.
- **Set `OPENWEATHER_API_KEY`** in your Hyprland env for the weather example.
- **Test from terminal**: `fabric-cli exec modus1 'deep_reload your_plugin_id'`
