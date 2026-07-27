# Desktop Widgets Guide

Modus displays widgets directly on your desktop background. Drop a `.py` file in `config/desktop/` and it appears live — no restart needed.

## Quick Start

Copy the example widget:

```bash
cp examples/desktop/example.py config/desktop/example.py
```

The widget appears on your desktop immediately. Edit positions by dragging in edit mode (right-click desktop → Edit Widgets) or by editing `config/desktop.toml`.

## How It Works

1. On startup, Modus scans `config/desktop/` for `.py` files.
2. Each file is imported. It calls `DesktopWidgetRegistry.register()` to register a widget class with a key, size, and default position.
3. `config/desktop.toml` stores per-monitor positions (`px`, `py` as 0.0–1.0 fractions).
4. A file monitor + 2-second poll watches `config/desktop/` — adding or removing files live-reloads widgets.

## Writing a Desktop Widget

### Minimal Example

File: `config/desktop/example.py`

```python
from fabric.widgets.box import Box
from fabric.widgets.label import Label

from window.desktop.registry import DesktopWidgetRegistry


class ExampleClockWidget(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="example-clock-widget",
            orientation="v",
            h_expand=True,
            v_expand=True,
            h_align="center",
            v_align="center",
            **kwargs,
        )
        self.label = Label(
            name="example-clock-label",
            label="Hello Desktop",
            justification="center",
        )
        self.add(self.label)


DesktopWidgetRegistry.register(
    "example",              # unique key (used in desktop.toml)
    ExampleClockWidget,       # GTK widget class
    (174, 174),               # size (width, height) in pixels
    (0.45, 0.45),             # default position (px, py) as 0.0–1.0 fractions
)
```

### `DesktopWidgetRegistry.register()` Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `key` | `str` | Yes | Unique identifier (e.g., `"my_widget"`). Used in `desktop.toml`. |
| `widget_cls` | `class` | Yes | GTK widget class (must inherit from a Fabric/GTK widget). |
| `size` | `tuple[int, int]` | Yes | `(width, height)` in pixels. |
| `default_position` | `tuple[float, float]` | No | `(px, py)` as 0.0–1.0 screen fractions. Default `(0.0, 0.0)`. |

### Widget Rules

- Widget must be a GTK widget (inherit from `fabric.widgets.box.Box`, `fabric.widgets.label.Label`, etc.)
- Use `name=` for CSS styling (maps to `#example-clock-widget` in CSS)
- Set `h_expand=True` / `v_expand=True` for flexible sizing
- Call `DesktopWidgetRegistry.register()` at module level (not inside a function)
- The `key` must be unique across all widgets

## Built-in Widgets

| Key | Widget | Default Position |
|-----|--------|-----------------|
| `date` | Date display | Top-left `(0.0, 0.0)` |
| `weather` | Weather info | Top-left `(0.097, 0.0)` |
| `calendar` | Monthly calendar | Top-left `(0.191, 0.001)` |
| `cpu_info` | CPU usage | Bottom-right `(0.810, 0.827)` |
| `ram_info` | RAM usage | Bottom-right `(0.905, 0.827)` |

## Positioning

### Edit Mode (Drag and Drop)

1. Right-click desktop → **Edit Widgets**
2. Drag widgets to new positions
3. Right-click → **Done Edit**
4. Positions save to `config/desktop.toml`

### Config File

Edit `config/desktop.toml` directly:

```toml
[[0]]
key = "my_widget"
px = 0.5
py = 0.5
```

- `0` = monitor ID (0 for primary)
- `px`, `py` = position as 0.0–1.0 fractions of screen

### Default Position

Set in your widget file's `register()` call. Used when no entry exists in `desktop.toml`:

```python
DesktopWidgetRegistry.register("my_widget", MyWidget, (174, 174), (0.3, 0.7))
```

## Lifecycle

| Action | What Happens |
|--------|-------------|
| Add `.py` file to `config/desktop/` | Widget appears on desktop (live) |
| Delete `.py` file from `config/desktop/` | Widget disappears (within 2s) |
| Edit `.py` file in `config/desktop/` | Widget rebuilds on next file change |
| Drag widget in edit mode | Position saves to `desktop.toml` |
| Edit `desktop.toml` manually | Position updates on restart |

## Styling Widgets

Use the widget's `name` parameter for CSS targeting:

```python
self.label = Label(name="my-widget-label", label="Hello")
```

In your CSS (`src/styles/`), target with:

```css
#my-widget-label {
    font-size: 24px;
    color: @theme_text_color;
}

#my-widget-label:selected {
    color: @accent_color;
}
```

## Advanced: Using Services

Widgets can access Modus services for live data:

```python
from fabric.utils import GLib, invoke_repeater
from fabric.widgets.box import Box
from fabric.widgets.label import Label

from window.desktop.registry import DesktopWidgetRegistry


class LiveClockWidget(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="live-clock",
            orientation="v",
            h_align="center",
            v_align="center",
            **kwargs,
        )
        self.label = Label(name="clock-label", label="--:--")
        self.add(self.label)
        self._timer_id = invoke_repeater(1000, self._update)

    def _update(self) -> bool:
        import datetime
        now = datetime.datetime.now()
        self.label.set_label(now.strftime("%H:%M"))
        return True

    def destroy(self):
        if hasattr(self, "_timer_id") and self._timer_id:
            GLib.source_remove(self._timer_id)
        super().destroy()


DesktopWidgetRegistry.register("live_clock", LiveClockWidget, (174, 174), (0.5, 0.0))
```

## Input Regions & Keybind Compatibility

The desktop widget window uses a **partial input region** — only the rectangular areas occupied by widgets receive pointer and keyboard input. Empty desktop space passes through to windows below.

This means:
- Hyprland keybinds (e.g., `Super+Q` minimize) work normally even with widgets visible
- Right-clicking on widget areas opens the edit context menu; right-clicking on empty desktop passes through
- Drag and drop works within widget areas

No configuration needed — this is automatic. If widgets ever interfere with keybinds, check that the widget's `size` in `register()` matches its actual rendered size.

## Troubleshooting

### Widget not appearing?

- Check the file is in `config/desktop/` (not a subdirectory)
- Check `journalctl --user -f -t modus` for `[DesktopWidgets]` errors
- Ensure the file calls `DesktopWidgetRegistry.register()` at module level
- Ensure the `key` is unique (not conflicting with built-in widgets)

### Widget still showing after deleting the file?

The file monitor + poll should clean up within 2 seconds. If not:
1. Check `journalctl --user -f -t modus` for `[DesktopWidgets] poll found stale:` messages
2. Restart Modus: `uv run start`

### Position resets after restart?

- `desktop.toml` stores your custom positions
- If you delete `desktop.toml`, positions revert to defaults from `register()` calls
- Ensure `config/desktop.toml` is writable
