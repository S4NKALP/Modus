import time
from pathlib import Path

from fabric.core.service import Property, Service, Signal
from fabric.utils import GLib, exec_shell_command_async, logger, os, re

from utils.functions import find_binary, run_command


class Brightness(Service):
    """Service for controlling screen brightness using ddcutil or brightnessctl backends.

    The service works with RAW values (0 to max_screen) for both backends:
    - brightnessctl: raw values are device-specific (e.g., 0-96000)
    - ddcutil: raw values are percentages (0-100)

    The 'screen' signal emits percentage values (0-100) for UI display.
    """

    _instance = None
    DDCUTIL_PARAMS = "--disable-dynamic-sleep --sleep-multiplier=0.05"
    MIN_CHANGE_THRESHOLD = 2
    CACHE_INTERVAL = 3
    POLL_INTERVAL = 500

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @Signal
    def screen(self, value: int) -> None:
        """Signal emitted when screen brightness changes (value: percentage from 0 to 100)."""

    def __init__(self, backend=None, **kwargs):
        """Initialize service with automatic backend detection."""
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        super().__init__(**kwargs)
        self._pending_raw = None
        self._timer_id = None
        self._poll_timer_id = None
        self._lock = GLib.Mutex()
        self._last_percent = -1
        self._last_raw = -1
        self._last_update_time = 0
        self._screen_device = None
        self._brightness_path = None
        self._max_brightness_path = None

        self.backend = self._detect_backend(backend)

        self.max_screen = self._read_max_brightness() or 100

        if self.backend:
            if self.backend == "ddcutil":
                GLib.timeout_add(100, lambda: self._update_brightness_cache())
            else:
                self._setup_polling()

    def _setup_polling(self):
        """Setup periodic polling of brightness file."""
        try:
            if self._brightness_path and self._brightness_path.exists():
                self._last_raw = int(self._brightness_path.read_text().strip())
                self._last_percent = (
                    int((self._last_raw / self.max_screen) * 100)
                    if self.max_screen > 0
                    else 0
                )

                self._poll_timer_id = GLib.timeout_add(
                    self.POLL_INTERVAL, self._check_brightness_file
                )
        except Exception as e:
            logger.error(f"Error setting up brightness polling: {e}")

    def _check_brightness_file(self):
        """Periodically check brightness file for changes."""
        try:
            if self._brightness_path and self._brightness_path.exists():
                raw = int(self._brightness_path.read_text().strip())

                if raw != self._last_raw:
                    self._last_raw = raw
                    percent = (
                        int((raw / self.max_screen) * 100) if self.max_screen > 0 else 0
                    )
                    if abs(percent - self._last_percent) >= self.MIN_CHANGE_THRESHOLD:
                        self._last_percent = percent
                        self.emit("screen", percent)
            return True
        except Exception as e:
            logger.error(f"Error checking brightness file: {e}")
            return True

    def _detect_backend(self, backend):
        """Detect appropriate backend for brightness control."""
        if backend:
            logger.info(f"Using forced backend: {backend}")
            return backend

        if find_binary("brightnessctl"):
            device = self._get_screen_device()
            if device:
                logger.info(f"Using brightnessctl backend with device: {device}")
                return "brightnessctl"
            else:
                logger.debug(
                    "brightnessctl is available but no backlight devices found in /sys/class/backlight/"
                )

        if find_binary("ddcutil"):
            bus = self._detect_ddcutil_bus()
            if bus != -1:
                self.ddcutil_bus = bus
                logger.info(f"Using ddcutil backend with I2C bus: {bus}")
                return "ddcutil"
            else:
                logger.debug(
                    "ddcutil is available but no DDC/CI capable monitors detected"
                )

        logger.warning(
            "No available backend for brightness control - no backlight devices or DDC/CI monitors found"
        )
        return None

    def _get_screen_device(self):
        """Return first backlight device from sysfs, cached."""
        if getattr(self, "_screen_device", None):
            return self._screen_device

        try:
            devices = os.listdir("/sys/class/backlight")
            if devices:
                self._screen_device = devices[0]
                base_path = Path(f"/sys/class/backlight/{self._screen_device}")
                self._brightness_path = base_path / "brightness"
                self._max_brightness_path = base_path / "max_brightness"
                return self._screen_device
        except Exception:
            pass
        return ""

    def _detect_ddcutil_bus(self):
        """Detect I2C bus number for ddcutil."""
        try:
            process = run_command(["ddcutil", "detect"], timeout=2)
            if process.returncode == 0:
                match = re.search(r"I2C bus:\s*/dev/i2c-(\d+)", process.stdout)
                return int(match.group(1)) if match else -1
            return -1
        except Exception:
            return -1

    def _read_max_brightness(self):
        """Read maximum brightness value"""
        if self.backend:
            if self.backend == "ddcutil":
                try:
                    process = run_command(
                        [
                            "ddcutil",
                            "--bus",
                            str(self.ddcutil_bus),
                            *self.DDCUTIL_PARAMS.split(),
                            "getvcp",
                            "10",
                        ],
                        timeout=2,
                    )

                    if process.returncode == 0:
                        match = re.search(
                            r"current value\s*=\s*(\d+)\s*,\s*max value\s*=\s*(\d+)",
                            process.stdout,
                        )
                        if match:
                            return int(match.group(2))
                except Exception as e:
                    logger.error(f"Error executing ddcutil: {e}")
            else:
                try:
                    if self._max_brightness_path and self._max_brightness_path.exists():
                        return int(self._max_brightness_path.read_text().strip())
                except Exception:
                    return None
        return None

    def _update_brightness_cache(self):
        """Update brightness cache with current value."""
        if self.backend == "ddcutil":
            self.screen_brightness
        return False

    @Property(int, "read-write")
    def screen_brightness(self):
        """Getter returns current brightness in RAW value (0 to max_screen)."""
        if not self.backend:
            return -1

        if self.backend == "brightnessctl":
            if self._last_raw != -1:
                return self._last_raw

            try:
                if self._brightness_path and self._brightness_path.exists():
                    raw = int(self._brightness_path.read_text().strip())
                    self._last_raw = raw
                    return raw
            except Exception as e:
                logger.error(f"Error reading brightness file: {e}")
            return -1
        elif self.backend == "ddcutil":
            if (
                time.time() - self._last_update_time < self.CACHE_INTERVAL
                and self._last_raw != -1
            ):
                return self._last_raw

            def on_ddcutil_success(stdout):
                match = re.search(
                    r"current value\s*=\s*(\d+)\s*,\s*max value\s*=\s*(\d+)",
                    stdout,
                )
                if match:
                    current = int(match.group(1))
                    if current != self._last_raw:
                        self._last_raw = current
                        percent = (
                            int((current / self.max_screen) * 100)
                            if self.max_screen > 0
                            else 0
                        )
                        # Emit to update UI when background fetch completes
                        self.emit("screen", percent)

            # Update cache timestamp immediately to prevent spamming async commands
            self._last_update_time = time.time()

            try:
                exec_shell_command_async(
                    f"ddcutil --bus {self.ddcutil_bus} {self.DDCUTIL_PARAMS} getvcp 10",
                    lambda exit_code, stdout, stderr: (
                        on_ddcutil_success(stdout)
                        if exit_code == 0
                        else logger.error(f"ddcutil error (code {exit_code}): {stderr}")
                    ),
                )
            except Exception as e:
                logger.error(f"Error executing ddcutil async: {e}")

            return self._last_raw if self._last_raw != -1 else 0
        return None

    @screen_brightness.setter
    def screen_brightness(self, value: int):
        """Setter accepts brightness value in RAW (0 to max_screen)."""
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
                return

            self._pending_raw = value
            self._last_raw = value

            if self._timer_id:
                GLib.source_remove(self._timer_id)
            self._timer_id = GLib.timeout_add(50, self._apply_brightness)
        finally:
            self._lock.unlock()

    def _apply_brightness(self):
        """Apply pending brightness change with optimized debouncing."""
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

            if self.backend == "brightnessctl":
                self.emit("screen", percent)
                exec_shell_command_async(
                    f"brightnessctl --device '{self._screen_device}' set {raw}"
                )
            elif self.backend == "ddcutil":
                self._last_update_time = time.time()
                self.emit("screen", percent)
                exec_shell_command_async(
                    f"ddcutil --bus {self.ddcutil_bus} {self.DDCUTIL_PARAMS} --terse setvcp 10 {raw}",
                    lambda exit_code, stdout, stderr: (
                        logger.error(f"ddcutil error (code {exit_code}): {stderr}")
                        if exit_code != 0
                        else None
                    ),
                )
        except Exception as e:
            logger.error(f"Error setting brightness: {e}")
        return False

    def cleanup(self):
        """Clean up resources when service is stopped."""
        if self._timer_id:
            GLib.source_remove(self._timer_id)
            self._timer_id = None

        if self._poll_timer_id:
            GLib.source_remove(self._poll_timer_id)
            self._poll_timer_id = None
