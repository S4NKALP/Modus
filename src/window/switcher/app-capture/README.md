# AppCapture

`AppCapture` is a high-performance, C-based Wayland library with GObject Introspection (GIR) bindings. It allows you to efficiently capture real-time window previews (thumbnails) on Hyprland directly from Python.

## How It Works

This module is designed to interact directly with the Wayland compositor using several Wayland protocols:

- `wlr-foreign-toplevel-management-unstable-v1`
- `hyprland-toplevel-mapping-v1`
- `hyprland-toplevel-export-v1`

### Concurrency and Damage Tracking

Instead of relying on inefficient Python polling loops, `AppCapture` is fully asynchronous and event-driven.

- **Concurrent Captures**: It allocates an isolated `FrameContext` for every capture request. This means you can safely fire dozens of concurrent capture requests for different windows without memory corruption or blocking the main thread.
- **Zero-CPU Damage Tracking**: When you request a frame, you can set `wait_for_damage = True`. `AppCapture` leverages Wayland's native damage tracking (`ignore_damage = 0`). The C-backend will pause the request and **only** wake up when the window actually repaints. This eliminates CPU polling overhead and allows 0% CPU consumption for static windows.
- **Native Scaling**: The captured SHM buffer is scaled directly in C using `Cairo`. The library takes a bounding box (`max_width`, `max_height`) and intelligently applies a uniform "contain" scale to fit the box perfectly while preserving the window's aspect ratio.

## How to Build

The project uses the **Meson** build system and generates a shared library (`libappcapture.so`) along with a GObject Introspection Typelib (`AppCapture-1.0.typelib`).

To build or recompile the module after making changes to the C code:

```bash
cd src/window/switcher/app-capture
meson setup builddir  # (Only needed the first time)
meson compile -C builddir
```

## How to Use (Python)

Once compiled, you can easily load the library into any Python script using PyGObject (`gi`). Ensure that the `builddir` is in your `GI_TYPELIB_PATH` and `LD_LIBRARY_PATH`.

### Minimal Example

```python
import gi

gi.require_version("AppCapture", "1.0")
from gi.repository import AppCapture


def on_frame_ready(capture, address, data, width, height, stride):
    # 'data' is a GLib.Bytes object containing the raw ARGB32 pixel data
    # Convert it to a Cairo Surface or GdkPixbuf
    print(f"Frame received for {address}! Size: {width}x{height}")

    # Example: Request the next frame, but wait for damage (0% CPU idle)
    capture.capture_by_handle(address, 300, 168, True)


def on_frame_failed(capture, address, reason):
    print(f"Failed to capture {address}: {reason}")


# 1. Initialize the capture module
capture = AppCapture.Capture()
capture.connect("frame-ready", on_frame_ready)
capture.connect("frame-failed", on_frame_failed)

# 2. Request a frame
window_address = "0x12345678"
max_width = 300
max_height = 168

# capture_by_handle(address, max_width, max_height, wait_for_damage)
# False: Capture instantly (ideal for initial preview)
# True: Suspend and wait for the window to visually update
capture.capture_by_handle(window_address, max_width, max_height, False)
```
