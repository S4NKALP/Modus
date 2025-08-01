# From https://github.com/stwa/wayland-idle-inhibitor
# License: WTFPL Version 2

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from signal import SIGINT, SIGTERM, signal
from threading import Event, Timer

import setproctitle
from pywayland.client.display import Display
from pywayland.protocol.idle_inhibit_unstable_v1.zwp_idle_inhibit_manager_v1 import (
    ZwpIdleInhibitManagerV1,
)
from pywayland.protocol.wayland.wl_compositor import WlCompositor
from pywayland.protocol.wayland.wl_registry import WlRegistryProxy
from pywayland.protocol.wayland.wl_surface import WlSurface


@dataclass
class GlobalRegistry:
    surface: WlSurface | None = None
    inhibit_manager: ZwpIdleInhibitManagerV1 | None = None


def parse_duration(duration_str: str) -> int:
    """Parse duration string into seconds.
    Examples: '1h', '30m', '45s', '1.5h', '1.5m', '30.5s', 'on', 'off'
    """
    try:
        if duration_str.lower() in ["on", "off"]:
            return 0
        elif duration_str.endswith("h"):
            return int(float(duration_str[:-1]) * 3600)
        elif duration_str.endswith("m"):
            return int(float(duration_str[:-1]) * 60)
        elif duration_str.endswith("s"):
            return int(float(duration_str[:-1]))
        else:
            return int(duration_str)
    except ValueError:
        raise ValueError(
            "Invalid duration format. Use '1h', '30m', '45s', 'on', 'off', etc."
        )


def kill_existing_inhibit_processes():
    """Kill any existing modus-inhibit processes."""
    try:
        # Find all modus-inhibit processes except the current one
        output = subprocess.check_output(["pgrep", "-f", "modus-inhibit"], text=True)
        pids = output.strip().split("\n")
        current_pid = str(os.getpid())

        killed_count = 0
        for pid in pids:
            pid = pid.strip()
            if pid and pid != current_pid:
                try:
                    subprocess.run(["kill", pid], check=True)
                    killed_count += 1
                except subprocess.CalledProcessError:
                    pass  # Process might have already exited

        if killed_count > 0:
            print(f"Stopped {killed_count} existing inhibit process(es)")
        else:
            print("No existing inhibit processes were running")
        return killed_count

    except subprocess.CalledProcessError:
        # No processes found
        print("No existing inhibit processes were running")
        return 0
    except Exception as e:
        print(f"Error stopping existing processes: {e}")
        return 0


def handle_registry_global(
    wl_registry: WlRegistryProxy, id_num: int, iface_name: str, version: int
) -> None:
    global_registry: GlobalRegistry = wl_registry.user_data or GlobalRegistry()

    if iface_name == "wl_compositor":
        compositor = wl_registry.bind(id_num, WlCompositor, version)
        global_registry.surface = compositor.create_surface()  # type: ignore
    elif iface_name == "zwp_idle_inhibit_manager_v1":
        global_registry.inhibit_manager = wl_registry.bind(
            id_num, ZwpIdleInhibitManagerV1, version
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inhibit system idle for a specified duration"
    )
    parser.add_argument(
        "duration",
        nargs="?",
        default="0",
        help='Duration to inhibit (e.g., "1h", "30m", "45s", "on", "off"). Use "on" for indefinite, "off" to stop.',
    )
    args = parser.parse_args()

    # Handle "off" argument - kill existing processes and exit
    if args.duration.lower() == "off":
        kill_existing_inhibit_processes()
        sys.exit(0)

    done = Event()
    signal(SIGINT, lambda _, __: done.set())
    signal(SIGTERM, lambda _, __: done.set())

    global_registry = GlobalRegistry()

    try:
        display = Display()
        display.connect()

        registry = display.get_registry()  # type: ignore
        registry.user_data = global_registry
        registry.dispatcher["global"] = handle_registry_global

        def shutdown() -> None:
            display.dispatch()
            display.roundtrip()
            display.disconnect()

        display.dispatch()
        display.roundtrip()

        if global_registry.surface is None:
            print("Error: Failed to create Wayland surface.")
            shutdown()
            sys.exit(1)

        if global_registry.inhibit_manager is None:
            print("Error: Your Wayland compositor does not support idle inhibition.")
            print("This usually means either:")
            print(
                "1. Your compositor (like Hyprland) doesn't support the idle-inhibit protocol"
            )
            print("2. The protocol is not enabled in your compositor")
            print("\nFor Hyprland, you can enable it by adding to your config:")
            print("misc:disable_autoreload = true")
            print("misc:enable_wayland_protocols = true")
            shutdown()
            sys.exit(1)

        inhibitor = global_registry.inhibit_manager.create_inhibitor(  # type: ignore
            global_registry.surface
        )

        display.dispatch()
        display.roundtrip()

        duration = parse_duration(args.duration)
        if duration > 0:
            print(f"Inhibiting idle for {args.duration}...")
            # Set up timer to release inhibition
            timer = Timer(duration, lambda: done.set())
            timer.start()
        else:
            print("Inhibiting idle indefinitely...")

        done.wait()
        print("Shutting down...")

        inhibitor.destroy()
        if duration > 0:
            timer.cancel()

        shutdown()

    except Exception as e:
        print(f"Error: {str(e)}")
        print("Make sure you're running this under a Wayland session.")
        sys.exit(1)


if __name__ == "__main__":
    setproctitle.setproctitle("modus-inhibit")
    main()
