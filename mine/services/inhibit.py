from dataclasses import dataclass
from threading import Event, Thread, Timer

from fabric.core.service import Property, Service, Signal
from fabric.utils import re
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
    ds = duration_str.strip().lower()
    m = re.fullmatch(r"(?:on|off)|(\d+(?:\.\d+)?)([hms]?)", ds) or (
        (_ for _ in ()).throw(
            ValueError(
                "Invalid duration format. Use '1h', '30m', '45s', 'on', 'off', etc."
            )
        )
    )
    value = float(m.group(1) or 0.0)
    unit = m.group(2) or "s"
    multipliers = {"h": 3600, "m": 60, "s": 1, "": 1}
    return int(value * multipliers[unit])


class InhibitService(Service):
    _instance = None

    @staticmethod
    def get_initial():
        if InhibitService._instance is None:
            InhibitService._instance = InhibitService()
        return InhibitService._instance

    @Signal
    def state_changed(self) -> None: ...

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._thread: Thread | None = None
        self._stop_event = Event()
        self._running = False
        self._duration_s = 0

    @Property(bool, "readable", default_value=False)
    def is_running(self) -> bool:
        return self._running

    def enable(self, duration: str) -> None:
        self.disable()
        self._duration_s = (
            0 if duration.strip().lower() == "on" else parse_duration(duration)
        )
        self._stop_event.clear()
        self._thread = Thread(target=self._run, daemon=True)
        self._thread.start()

    def disable(self) -> None:
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=1.0)
        self._thread = None

    def _run(self) -> None:
        display = Display()
        display.connect()

        registry = display.get_registry()  # type: ignore
        global_registry = GlobalRegistry()
        registry.user_data = global_registry
        registry.dispatcher["global"] = handle_registry_global

        display.dispatch()
        display.roundtrip()

        if global_registry.surface is None or global_registry.inhibit_manager is None:
            display.disconnect()
            return

        inhibitor = global_registry.inhibit_manager.create_inhibitor(  # type: ignore
            global_registry.surface
        )

        self._running = True
        self.emit("state_changed")

        timer = (
            Timer(self._duration_s, lambda: self._stop_event.set())
            if self._duration_s > 0
            else None
        )
        if timer:
            timer.start()

        try:
            while not self._stop_event.is_set():
                display.dispatch()
                display.roundtrip()
        finally:
            inhibitor.destroy()
            if timer:
                timer.cancel()
            display.disconnect()
            self._running = False
            self.emit("state_changed")


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
