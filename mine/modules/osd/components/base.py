import contextlib
from abc import abstractmethod

from fabric.utils import Gdk, GLib, idle_add, invoke_repeater, remove_handler, time
from fabric.widgets.box import Box
from fabric.widgets.wayland import WaylandWindow as Window


class BaseOSDContainer(Box):
    MAX_VISIBLE_TIME = 6.0  # Increased for safety: 1.7s focus + 1.7s unfocus + margin
    COOLDOWN_MS = 200  # Minimum time between OSD triggers (milliseconds)

    def __init__(self, window: Window, **kwargs):
        super().__init__(**kwargs, spacing=12, name="osd-container")
        self.last_handler: int = 0
        self.window = window
        self.osd = None
        self.show_timestamp: float = 0.0
        self.watchdog_handler: int = 0
        self._update_in_progress = False  # Prevent concurrent updates
        self._is_hovered = False
        self._last_trigger_time: float = 0.0  # Track last trigger time for cooldown

        # Defer signal connection until window is initialized
        idle_add(self._setup_window_signals)

    def _setup_window_signals(self):
        self.window.add_events(
            Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK
        )
        self.window.connect("enter-notify-event", self._on_enter_notify)
        self.window.connect("leave-notify-event", self._on_leave_notify)
        return False

    def _on_enter_notify(self, widget, event):
        if event.detail != Gdk.NotifyType.INFERIOR:
            self._is_hovered = True

    def _on_leave_notify(self, widget, event):
        if event.detail != Gdk.NotifyType.INFERIOR:
            self._is_hovered = False

    def is_hovered(self):
        return self._is_hovered

    def remove_last_handler(self):
        if self.last_handler:
            with contextlib.suppress(Exception):
                remove_handler(self.last_handler)
            self.last_handler = 0

    def remove_watchdog_handler(self):
        if self.watchdog_handler:
            with contextlib.suppress(Exception):
                GLib.source_remove(self.watchdog_handler)
            self.watchdog_handler = 0

    def cleanup_all_handlers(self):
        """Clean up all handlers and reset state."""
        self.remove_last_handler()
        self.remove_watchdog_handler()
        self.show_timestamp = 0.0
        self._update_in_progress = False

    def watchdog_force_hide(self, *_):
        """Failsafe timer to force-hide OSD if normal sequence fails."""
        if not self.window.get_visible():
            self.cleanup_all_handlers()
            return False

        # Check if we've exceeded maximum visible time
        elapsed = time.time() - self.show_timestamp
        if elapsed >= self.MAX_VISIBLE_TIME:
            if not self.is_hovered():
                self.window.hide()
                self.cleanup_all_handlers()
                return False
            else:
                # Still hovered, check again in 1 second
                return True

        return True  # Keep checking

    def update(self, *_):
        # Prevent concurrent updates
        if self._update_in_progress:
            return

        # Check cooldown to prevent spam
        current_time = time.time()
        time_since_last_trigger = (
            current_time - self._last_trigger_time
        ) * 1000  # Convert to ms

        if time_since_last_trigger < self.COOLDOWN_MS:
            return  # Still in cooldown period, ignore this trigger

        self._last_trigger_time = current_time
        self._update_in_progress = True

        # Clean up any existing timers
        self.cleanup_all_handlers()

        # Record show time and display window
        self.show_timestamp = time.time()
        self.window.show()

        # Start animation sequence
        self.focus()

        # Schedule unfocus after focus animation completes
        self.last_handler = invoke_repeater(1700, self.unfocus, initial_call=False)

        # Start watchdog timer (checks every second)
        self.watchdog_handler = GLib.timeout_add(1000, self.watchdog_force_hide)

        self._update_in_progress = False

    def focus(self, *_):
        self.style_classes = "focused"
        return False

    def unfocus(self, *_):
        if not self.window.get_visible():
            self.cleanup_all_handlers()
            return False

        self.style_classes = ()
        self.remove_last_handler()

        # Schedule hide after unfocus animation
        self.last_handler = invoke_repeater(1700, self.unpop, initial_call=False)
        return False

    def unpop(self, *_):
        if not self.window.get_visible():
            self.cleanup_all_handlers()
            return False

        if not self.is_hovered():
            self.window.hide()
            self.cleanup_all_handlers()
        else:
            # User is hovering, check again in 500ms
            self.last_handler = invoke_repeater(500, self.unpop, initial_call=False)

        return False

    @abstractmethod
    def _setup_specific_components(self):
        pass

    @abstractmethod
    def _connect_specific_signals(self):
        pass
