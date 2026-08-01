from functools import partial

from fabric.utils import logger
from gi.repository import Gdk, Gtk

from utils.functions import run_command, thread


class ModusDropdown:
    """Reusable Gtk.Menu-based dropdown."""

    def __init__(self, items=None):
        self._menu = Gtk.Menu()
        self._source_button = None
        self._menu.connect("hide", self._on_menu_hide)

        if items:
            self._build(items)

    @property
    def menu(self):
        return self._menu

    def _build(self, items):
        for entry in items:
            item = self._create_item(entry)
            if item is not None:
                self._menu.append(item)
        self._menu.show_all()

    def _create_item(self, entry):
        if entry is None:
            return Gtk.SeparatorMenuItem()

        if isinstance(entry, Gtk.Widget):
            return entry

        if isinstance(entry, dict):
            return self._make_item(entry)

        label, callback = entry[0], entry[1]
        sensitive = entry[2] if len(entry) > 2 else True
        item = Gtk.MenuItem.new_with_label(label)
        if sensitive and callback:
            item.connect("activate", callback)
        elif not sensitive:
            item.set_sensitive(False)
        return item

    def _make_item(self, entry):
        label = entry.get("label", "")
        accel = entry.get("accel")
        command = entry.get("command")
        callback = entry.get("callback")
        sensitive = entry.get("sensitive", True)

        if accel:
            label = f"{label}    {accel}"

        item = Gtk.MenuItem.new_with_label(label)
        if not sensitive:
            item.set_sensitive(False)
        elif callback or command:
            item.connect(
                "activate",
                partial(self._activate, callback, command),
            )
        return item

    @staticmethod
    def _activate(callback, command, *args):
        if callback:
            callback(*args)
        if command:
            thread(run_command, ["sh", "-c", command], timeout=30)

    def _on_menu_hide(self, *_):
        if not self._source_button:
            return
        try:
            self._source_button.unset_state_flags(Gtk.StateFlags.ACTIVE)
            self._source_button.queue_draw()
        except Exception:
            logger.exception("[ModusDropdown] failed to reset button state")
        self._source_button = None

    def append(self, item):
        created = self._create_item(item)
        if created is not None:
            self._menu.append(created)
            self._menu.show_all()

    def clear(self):
        for child in self._menu.get_children():
            child.destroy()

    def popup_at_widget(self, widget, source_button=None):
        self._source_button = source_button or widget
        self._menu.popup_at_widget(
            widget,
            Gdk.Gravity.SOUTH_WEST,
            Gdk.Gravity.NORTH_WEST,
            None,
        )

    def popup(self, widget, source_button=None):
        self.popup_at_widget(widget, source_button)

    def destroy(self):
        """Destroy the Gtk.Menu and its children."""
        self._menu.destroy()


def dropdown_option(label, accel=None, command=None, callback=None, sensitive=True):
    """Create a dropdown menu option dict.

    Usage:
        dropdown_option("Lock Screen", "󰘳     L", "fabric-cli exec modus 'lock_screen.lock()'")
        dropdown_option("Settings", callback=my_func)
        dropdown_option("Disabled Item", sensitive=False)
    """
    return {
        "label": label,
        "accel": accel,
        "command": command,
        "callback": callback,
        "sensitive": sensitive,
    }
