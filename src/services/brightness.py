from pathlib import Path

from fabric.core.service import Property, Service, Signal
from fabric.utils import Gio, GLib, logger, os

LOGIND_BUS_NAME = "org.freedesktop.login1"
LOGIND_SESSION_PATH = "/org/freedesktop/login1/session/auto"
LOGIND_SESSION_IFACE = "org.freedesktop.login1.Session"


class Brightness(Service):
    """Service for controlling screen brightness via logind DBus.

    Uses org.freedesktop.login1.Session.SetBrightness for kernel backlight.
    'screen' signal emits percentage (0-100).
    """

    _instance = None
    MIN_CHANGE_THRESHOLD = 1

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @Signal
    def screen(self, value: int) -> None:
        """Emitted on brightness change. value: percentage 0-100."""

    def __init__(self, **kwargs):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        super().__init__(**kwargs)

        self._pending_raw = None
        self._timer_id = None
        self._poll_id = None
        self._file_monitor = None
        self._lock = GLib.Mutex()
        self._last_percent = -1
        self._last_raw = -1
        self._screen_device = None
        self._brightness_path = None
        self._max_brightness_path = None
        self._dbus_proxy = None

        self._screen_device = self._get_screen_device()
        self.max_screen = self._read_max_brightness() or 100

        if self._screen_device:
            self._init_logind()
            self._setup_monitoring()
            logger.info(
                f"[Brightness] logind backend ready, device={self._screen_device}, max={self.max_screen}"
            )
        else:
            logger.warning("[Brightness] No backlight device found")

    def _init_logind(self):
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            self._dbus_proxy = Gio.DBusProxy.new_sync(
                bus,
                Gio.DBusProxyFlags.NONE,
                None,
                LOGIND_BUS_NAME,
                LOGIND_SESSION_PATH,
                LOGIND_SESSION_IFACE,
                None,
            )
            logger.info("[Brightness] logind Session proxy initialized")
        except Exception as e:
            logger.error(f"[Brightness] Failed to init logind proxy: {e}")

    def _get_screen_device(self):
        try:
            devices = os.listdir("/sys/class/backlight")
            if devices:
                self._screen_device = devices[0]
                base = Path(f"/sys/class/backlight/{self._screen_device}")
                self._brightness_path = base / "brightness"
                self._max_brightness_path = base / "max_brightness"
                return self._screen_device
        except Exception as e:
            logger.warning(f"[Brightness] Failed to enumerate backlight: {e}")
        return None

    def _read_max_brightness(self):
        try:
            if self._max_brightness_path and self._max_brightness_path.exists():
                return int(self._max_brightness_path.read_text().strip())
        except Exception as e:
            logger.warning(f"[Brightness] Failed to read max_brightness: {e}")
        return None

    def _setup_monitoring(self):
        try:
            if self._brightness_path and self._brightness_path.exists():
                self._last_raw = int(self._brightness_path.read_text().strip())
                self._last_percent = (
                    int((self._last_raw / self.max_screen) * 100)
                    if self.max_screen > 0
                    else 0
                )
                brightness_file = Gio.File.new_for_path(str(self._brightness_path))
                self._file_monitor = brightness_file.monitor_file(
                    Gio.FileMonitorFlags.NONE, None
                )
                self._file_monitor.connect("changed", self._on_brightness_file_changed)
                logger.info("[Brightness] File monitor active")
        except Exception as e:
            logger.error(f"[Brightness] Failed to setup monitor: {e}")

    def _on_brightness_file_changed(self, _monitor, _file, _other_file, event_type):
        if event_type != Gio.FileMonitorEvent.CHANGED:
            return
        self._sync_from_sysfs()

    def _sync_from_sysfs(self):
        try:
            if not self._brightness_path or not self._brightness_path.exists():
                return
            raw = int(self._brightness_path.read_text().strip())
            if raw == self._last_raw:
                return
            self._last_raw = raw
            percent = int((raw / self.max_screen) * 100) if self.max_screen > 0 else 0
            if abs(percent - self._last_percent) >= self.MIN_CHANGE_THRESHOLD:
                self._last_percent = percent
                self.emit("screen", percent)
        except Exception as e:
            logger.error(f"[Brightness] Error reading brightness: {e}")

    def _set_brightness_logind(self, device_name: str, value: int):
        if not self._dbus_proxy:
            return
        try:
            self._dbus_proxy.call(
                "SetBrightness",
                GLib.Variant("(ssu)", ("backlight", device_name, value)),
                Gio.DBusCallFlags.NONE,
                -1,
                None,
                None,
            )
        except Exception as e:
            logger.error(f"[Brightness] logind SetBrightness failed: {e}")

    @Property(int, "read-write")
    def screen_brightness(self):
        """Current brightness in RAW value (0 to max_screen)."""
        if self._last_raw != -1:
            return self._last_raw
        try:
            if self._brightness_path and self._brightness_path.exists():
                raw = int(self._brightness_path.read_text().strip())
                self._last_raw = raw
                return raw
        except Exception as e:
            logger.error(f"[Brightness] Error reading brightness: {e}")
        return -1

    @screen_brightness.setter
    def screen_brightness(self, value: int):
        self._lock.lock()
        try:
            value = max(0, min(value, self.max_screen))

            current_percent = (
                int((self._last_raw / self.max_screen) * 100)
                if self._last_raw != -1 and self.max_screen > 0
                else -1
            )
            new_percent = (
                int((value / self.max_screen) * 100) if self.max_screen > 0 else 0
            )

            if (
                abs(new_percent - current_percent) < self.MIN_CHANGE_THRESHOLD
                and self._last_raw != -1
            ):
                self.emit("screen", new_percent)
                return

            self._pending_raw = value
            self._last_raw = value

            if self._timer_id:
                GLib.source_remove(self._timer_id)
            self._timer_id = GLib.timeout_add(50, self._apply_brightness)
        finally:
            self._lock.unlock()

    def _apply_brightness(self):
        self._lock.lock()
        try:
            if self._pending_raw is None:
                self._timer_id = None
                return False
            raw = self._pending_raw
            self._pending_raw = None
            self._timer_id = None
        finally:
            self._lock.unlock()

        try:
            percent = int((raw / self.max_screen) * 100) if self.max_screen > 0 else 0
            self.emit("screen", percent)
            self._set_brightness_logind(self._screen_device, raw)
        except Exception as e:
            logger.error(f"[Brightness] Error setting brightness: {e}")
        return False

    def cleanup(self):
        if self._timer_id:
            GLib.source_remove(self._timer_id)
            self._timer_id = None
        if self._poll_id:
            GLib.source_remove(self._poll_id)
            self._poll_id = None
        if self._file_monitor:
            self._file_monitor.cancel()
            self._file_monitor = None
