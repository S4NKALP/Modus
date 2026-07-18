from abc import abstractmethod

from fabric.utils import Gdk, GLib, invoke_repeater, logger, remove_handler, time
from fabric.widgets.box import Box
from fabric.widgets.wayland import WaylandWindow as Window


class BaseOSDContainer(Box):
    MAX_VISIBLE_TIME = 6.0
    COOLDOWN_MS = 200

    def __init__(self, window: Window, **kwargs):
        super().__init__(**kwargs, orientation="v", spacing=12, name="osd-container")
        self.last_handler: int = 0
        self.window = window
        self.osd = None
        self.show_timestamp: float = 0.0
        self.watchdog_handler: int = 0
        self._hide_timer_id: int | None = None
        self._update_in_progress = False
        self._is_hovered = False
        self._last_trigger_time: float = 0.0

        GLib.idle_add(self._setup_window_signals)

    def _setup_window_signals(self):
        self.window.add_events(
            Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK
        )
        self.window.connect("enter-notify-event", self._on_enter_notify)
        self.window.connect("leave-notify-event", self._on_leave_notify)
        return False

    def destroy(self):
        self._cancel_hide_timer()
        self.cleanup_all_handlers()
        super().destroy()

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
            try:
                remove_handler(self.last_handler)
            except Exception as e:
                logger.error(f"An error occurred: {e}")
            self.last_handler = 0

    def remove_watchdog_handler(self):
        if self.watchdog_handler:
            try:
                GLib.source_remove(self.watchdog_handler)
            except Exception as e:
                logger.error(f"An error occurred: {e}")
            self.watchdog_handler = 0

    def cleanup_all_handlers(self):
        self.remove_last_handler()
        self.remove_watchdog_handler()
        self.show_timestamp = 0.0
        self._update_in_progress = False

    def _cancel_hide_timer(self):
        if self._hide_timer_id is not None:
            try:
                GLib.source_remove(self._hide_timer_id)
            except Exception as e:
                logger.debug(f"[osd_base] Failed to remove hide timer {self._hide_timer_id}: {e}")
            self._hide_timer_id = None

    def hide_window(self):
        self._cancel_hide_timer()
        if self.osd and hasattr(self.osd, "revealer"):
            self.osd.revealer.set_reveal_child(False)
            self._hide_timer_id = GLib.timeout_add(150, self._on_hide_timer_done)
        else:
            self.window.hide()

    def _on_hide_timer_done(self):
        self._hide_timer_id = None
        self.window.hide()
        return False

    def watchdog_force_hide(self, *_):
        if not self.window.get_visible():
            self.cleanup_all_handlers()
            return False

        elapsed = time.time() - self.show_timestamp
        if elapsed >= self.MAX_VISIBLE_TIME:
            if not self.is_hovered():
                self.hide_window()
                self.cleanup_all_handlers()
                return False
            else:
                return True
        return True

    def update(self, *_):
        if self._update_in_progress:
            return

        current_time = time.time()
        time_since_last_trigger = (current_time - self._last_trigger_time) * 1000

        if time_since_last_trigger < self.COOLDOWN_MS:
            return

        self._last_trigger_time = current_time
        self._update_in_progress = True

        self.cleanup_all_handlers()
        self.show_timestamp = time.time()

        if self.osd:
            self.osd.show_container(self)

        self.window.show()

        self.focus()
        self.last_handler = invoke_repeater(1700, self.unfocus, initial_call=False)
        self.watchdog_handler = GLib.timeout_add(1000, self.watchdog_force_hide)
        self._update_in_progress = False

    def focus(self, *_):
        self.add_style_class("focused")
        return False

    def unfocus(self, *_):
        if not self.window.get_visible():
            self.cleanup_all_handlers()
            return False

        self.remove_style_class("focused")
        self.remove_last_handler()
        self.last_handler = invoke_repeater(1700, self.unpop, initial_call=False)
        return False

    def unpop(self, *_):
        if not self.window.get_visible():
            self.cleanup_all_handlers()
            return False

        if not self.is_hovered():
            self.hide_window()
            self.cleanup_all_handlers()
        else:
            self.last_handler = invoke_repeater(500, self.unpop, initial_call=False)
        return False

    @abstractmethod
    def _setup_specific_components(self):
        pass

    @abstractmethod
    def _connect_specific_signals(self):
        pass
