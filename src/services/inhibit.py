from fabric.core.service import Property, Service, Signal
from fabric.utils import Gio, GLib, logger

_BUS_NAME = "org.freedesktop.ScreenSaver"
_OBJECT_PATH = "/org/freedesktop/ScreenSaver"
_INTERFACE = "org.freedesktop.ScreenSaver"


class InhibitService(Service):
    """Service for managing idle inhibition via org.freedesktop.ScreenSaver D-Bus."""

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @Signal
    def inhibit_changed(self, active: bool) -> None:
        """Signal emitted when inhibit state changes."""

    def __init__(self, **kwargs):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        super().__init__(**kwargs)
        self._cookie: int | None = None
        self._proxy: Gio.DBusProxy | None = None
        self._timer_source: int | None = None

    @Property(bool, "readable", default_value=False)
    def active(self) -> bool:
        return self._cookie is not None

    def _get_proxy(self) -> Gio.DBusProxy | None:
        if self._proxy is not None:
            return self._proxy
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            if bus is None:
                return None
            self._proxy = Gio.DBusProxy.new_sync(
                bus,
                Gio.DBusProxyFlags.NONE,
                None,
                _BUS_NAME,
                _OBJECT_PATH,
                _INTERFACE,
                None,
            )
            return self._proxy
        except Exception as e:
            logger.error(f"[InhibitService] Failed to create D-Bus proxy: {e}")
            return None

    def enable(self) -> bool:
        if self.active:
            return True
        proxy = self._get_proxy()
        if proxy is None:
            return False
        try:
            result = proxy.call_sync(
                "Inhibit",
                GLib.Variant("(ss)", ("Modus", "Caffeine mode")),
                Gio.DBusCallFlags.NONE,
                -1,
                None,
            )
            if result is not None:
                self._cookie = result.unpack()[0]
                self.emit("inhibit-changed", True)
                return True
            return False
        except Exception as e:
            logger.error(f"[InhibitService] Failed to inhibit: {e}")
            return False

    def enable_timed(self, seconds: int) -> bool:
        """Enable inhibition for *seconds*, then auto-disable."""
        self._cancel_timer()
        if not self.enable():
            return False
        self._timer_source = GLib.timeout_add_seconds(seconds, self._on_timer_done)
        return True

    def _on_timer_done(self) -> bool:
        self._timer_source = None
        self.disable()
        return False  # remove the source

    def _cancel_timer(self) -> None:
        if self._timer_source is not None:
            GLib.source_remove(self._timer_source)
            self._timer_source = None

    def disable(self) -> bool:
        if not self.active:
            return True
        self._cancel_timer()
        proxy = self._get_proxy()
        if proxy is None or self._cookie is None:
            return False
        try:
            proxy.call_sync(
                "Uninhibit",
                GLib.Variant("(u)", (self._cookie,)),
                Gio.DBusCallFlags.NONE,
                -1,
                None,
            )
            self._cookie = None
            self.emit("inhibit-changed", False)
            return True
        except Exception as e:
            logger.error(f"[InhibitService] Failed to uninhibit: {e}")
            return False

    def toggle(self) -> bool:
        if self.active:
            self.disable()
            return False
        else:
            self.enable()
            return True


def get_inhibit_service() -> InhibitService:
    return InhibitService()
