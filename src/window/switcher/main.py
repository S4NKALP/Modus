from collections import OrderedDict

from fabric.utils import Gdk, GdkPixbuf, GLib, logger
from fabric.widgets.box import Box
from fabric.widgets.eventbox import EventBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.overlay import Overlay
from fabric.widgets.wayland import WaylandWindow as Window

from services.config import config, on_config_change
from services.modus import close_window, focus_window, get_active_window, get_clients
from utils.functions import is_special_workspace
from utils.icon_resolver import IconResolver


class _SwitcherItem:
    __slots__ = (
        "button",
        "item_box",
        "icon_box",
        "name_label",
        "image",
        "overlay",
        "badge_box",
        "badge_label",
        "address",
    )

    def __init__(
        self,
        button,
        item_box,
        icon_box,
        name_label,
        image,
        overlay,
        badge_box,
        badge_label,
        address,
    ):
        self.button = button
        self.item_box = item_box
        self.icon_box = icon_box
        self.name_label = name_label
        self.image = image
        self.overlay = overlay
        self.badge_box = badge_box
        self.badge_label = badge_label
        self.address = address


class ApplicationSwitcher(Window):
    def __init__(self, **kwargs):
        super().__init__(
            name="application-switcher",
            title="modus-switcher",
            layer="top",
            anchor="center",
            keyboard_mode="exclusive",
            visible=False,
            **kwargs,
        )

        self.icon_resolver = IconResolver()
        self.windows: list[dict] = []
        self.current_index = 0
        self._prev_index = -1
        self.icon_size = 80
        self._pixbuf_cache: OrderedDict = OrderedDict()
        self._items: list[_SwitcherItem] = []
        self._pending_close = None

        on_config_change(self._on_config_changed)

        self.view = Box(
            name="app-switcher-view",
            orientation="h",
            spacing=4,
            h_align="center",
            v_align="center",
        )

        container = Box(
            name="app-switcher-container",
            orientation="v",
            h_align="center",
            v_align="center",
            children=[self.view],
        )
        self.add(container)

        self.connect("key-press-event", self.on_key_press)
        self.connect("key-release-event", self.on_key_release)

        self.show_all()
        self.set_visible(False)

    def _on_config_changed(self, new_config, old_config):
        if config().has_changed("hide_special_workspace", old_config):
            if self.get_visible():
                self._rebuild()

    def show_switcher(self) -> None:
        self._rebuild()
        if not self.windows:
            return

        self.set_opacity(0.0)
        self.show()
        self.ungrab_keyboard()
        self.grab_keyboard()
        GLib.timeout_add(16, self._fade_in)

    def _fade_in(self):
        current = self.get_opacity()
        if current >= 1.0:
            return False
        self.set_opacity(min(1.0, current + 0.15))
        return True

    def hide_switcher(self) -> None:
        self.set_opacity(0.0)
        if self._pending_close is not None:
            close_window(self._pending_close)
            self._pending_close = None
        GLib.timeout_add(150, self.hide)
        self.ungrab_keyboard()

    def _get_pixbuf(self, class_name: str) -> GdkPixbuf.Pixbuf | None:
        key = (class_name, self.icon_size)
        if key in self._pixbuf_cache:
            return self._pixbuf_cache[key]

        if len(self._pixbuf_cache) > 128:
            self._pixbuf_cache.popitem(last=False)

        pixbuf = self.icon_resolver.get_icon_pixbuf(class_name, self.icon_size)
        if not pixbuf:
            pixbuf = self.icon_resolver.get_icon_pixbuf(
                "application-x-executable-symbolic", self.icon_size
            )
        if pixbuf:
            self._pixbuf_cache[key] = pixbuf
        return pixbuf

    def _create_item(self) -> _SwitcherItem:
        image = Image()
        overlay = Overlay(child=image)

        name_label = Label(
            label="",
            name="app-switcher-item-label",
            h_align="center",
        )

        icon_box = Box(
            name="app-switcher-icon-box",
            children=[overlay],
            h_align="center",
            v_align="center",
        )

        item_box = Box(
            name="app-switcher-item",
            orientation="v",
            h_align="center",
            v_align="center",
            spacing=2,
            children=[icon_box, name_label],
        )

        event_box = EventBox(
            name="app-switcher-button",
            child=item_box,
            events=["button-press-event"],
            can_focus=False,
        )
        event_box.connect("button-press-event", self._on_item_clicked)
        event_box.connect("enter-notify-event", self._on_item_enter)
        event_box.connect("leave-notify-event", self._on_item_leave)

        return _SwitcherItem(
            button=event_box,
            item_box=item_box,
            icon_box=icon_box,
            name_label=name_label,
            image=image,
            overlay=overlay,
            badge_box=None,
            badge_label=None,
            address=None,
        )

    def _clear_states(self):
        for item in self._items:
            item.button.remove_style_class("hovered")
            item.button.remove_style_class("selected")
            item.name_label.set_opacity(0.0)

    def _rebuild(self) -> None:
        try:
            self._prev_index = -1
            self._clear_states()

            for child in list(self.view.get_children()):
                if not any(item.button == child for item in self._items):
                    self.view.remove(child)
                    child.destroy()

            clients = get_clients()
            if not clients:
                self.windows = []
                for item in self._items:
                    item.button.set_visible(False)
                return

            hide_special = config().get("hide_special_workspace", True)
            filtered = []
            for c in clients:
                if c.get("hidden", False):
                    continue
                if hide_special and is_special_workspace(c):
                    continue
                filtered.append(c)

            active = get_active_window()
            active_addr = active.get("address") if active else None
            if active_addr:
                idx = next(
                    (
                        i
                        for i, w in enumerate(filtered)
                        if w.get("address") == active_addr
                    ),
                    None,
                )
                if idx is not None and idx > 0:
                    filtered.insert(0, filtered.pop(idx))

            self.windows = [
                {
                    "address": w["address"],
                    "class": w.get("class") or "Unknown",
                    "workspace_id": w.get("workspace", {}).get("id"),
                }
                for w in filtered
            ]
            self.current_index = 0

            while len(self._items) < len(self.windows):
                item = self._create_item()
                self._items.append(item)
                self.view.add(item.button)

            for i, item in enumerate(self._items):
                visible = i < len(self.windows)
                item.button.set_visible(visible)
                if not visible:
                    item.button.remove_style_class("hovered")

            for i, item in enumerate(self._items[: len(self.windows)]):
                win = self.windows[i]
                item.address = win["address"]

                pixbuf = self._get_pixbuf(win["class"].lower())
                if pixbuf:
                    item.image.set_from_pixbuf(pixbuf)
                item.name_label.set_text(win["class"])

                ws_id = win["workspace_id"]
                if ws_id is not None:
                    if item.badge_box is None:
                        badge_label = Label(
                            label=str(ws_id),
                            name="app-switcher-workspace-badge-text",
                        )
                        badge_box = Box(
                            name="app-switcher-workspace-badge",
                            children=[badge_label],
                            h_align="end",
                            v_align="end",
                        )
                        item.overlay.add_overlay(badge_box)
                        item.badge_box = badge_box
                        item.badge_label = badge_label
                    else:
                        item.badge_label.set_text(str(ws_id))
                    item.badge_box.set_visible(True)
                else:
                    if item.badge_box is not None:
                        item.badge_box.set_visible(False)

            self._update_selection()
        except Exception:
            logger.exception("Failed to build switcher")

    def on_key_press(self, _, event):
        try:
            return self._on_key_press_impl(_, event)
        except Exception:
            logger.exception("on_key_press error")
            return False

    def _on_key_press_impl(self, _, event):
        keyval = event.keyval
        state = event.state
        name = Gdk.keyval_name(keyval)

        if not self.windows:
            return False

        if keyval == Gdk.KEY_Escape:
            self.hide_switcher()
            return True

        if name in ("Tab", "ISO_Left_Tab", "KP_Tab"):
            if state & Gdk.ModifierType.SHIFT_MASK or name == "ISO_Left_Tab":
                self.current_index = (self.current_index - 1) % len(self.windows)
            else:
                self.current_index = (self.current_index + 1) % len(self.windows)
            self._update_selection()
            return True

        if keyval in (Gdk.KEY_Right, Gdk.KEY_l):
            self.current_index = (self.current_index + 1) % len(self.windows)
            self._update_selection()
            return True

        if keyval in (Gdk.KEY_Left, Gdk.KEY_h):
            self.current_index = (self.current_index - 1) % len(self.windows)
            self._update_selection()
            return True

        if keyval in (Gdk.KEY_Delete, Gdk.KEY_BackSpace):
            self._close_selected()
            return True

        return False

    def on_key_release(self, _, event):
        keyval = event.keyval
        if keyval in (Gdk.KEY_Alt_L, Gdk.KEY_Alt_R):
            self._activate_selected()
            self.hide_switcher()
            return True
        return False

    def _update_selection(self):
        try:
            if self._prev_index >= 0 and self._prev_index < len(self._items):
                prev = self._items[self._prev_index]
                prev.button.remove_style_class("selected")
                prev.name_label.set_opacity(0.0)

            if self.current_index < len(self._items):
                curr = self._items[self.current_index]
                curr.button.add_style_class("selected")
                curr.name_label.set_opacity(1.0)

            self._prev_index = self.current_index
        except Exception:
            logger.exception("_update_selection error")

    def _activate_selected(self):
        if not self.windows or self.current_index >= len(self.windows):
            return
        address = self.windows[self.current_index]["address"]
        if address:
            focus_window(address)

    def _close_selected(self):
        try:
            self._close_selected_impl()
        except Exception:
            logger.exception("_close_selected error")

    def _close_selected_impl(self):
        if not self.windows or self.current_index >= len(self.windows):
            return

        idx = self.current_index
        self._pending_close = self.windows[idx]["address"]

        item = self._items.pop(idx)
        item.button.set_visible(False)

        self.windows.pop(idx)

        if not self.windows:
            self.hide_switcher()
            return

        if idx < self.current_index:
            self.current_index -= 1
        elif self.current_index >= len(self.windows):
            self.current_index = len(self.windows) - 1

        self._prev_index = -1
        self._update_selection()

    def _on_item_clicked(self, event_box, _event):
        for i, item in enumerate(self._items):
            if item.button == event_box:
                self.current_index = i
                break
        self._activate_selected()
        self.hide_switcher()
        return True

    def _on_item_enter(self, event_box, _event):
        event_box.add_style_class("hovered")
        return False

    def _on_item_leave(self, event_box, _event):
        event_box.remove_style_class("hovered")
        return False

    def grab_keyboard(self):
        try:
            display = Gdk.Display.get_default()
            seat = display.get_default_seat()
            window = self.get_window()
            status = seat.grab(
                window, Gdk.SeatCapabilities.KEYBOARD, False, None, None, None
            )
            if status != Gdk.GrabStatus.SUCCESS:
                logger.warning(f"Keyboard grab failed: {status}")
        except Exception:
            logger.exception("Failed to grab keyboard")

    def ungrab_keyboard(self):
        try:
            display = Gdk.Display.get_default()
            seat = display.get_default_seat()
            seat.ungrab()
        except Exception:
            logger.exception("Failed to ungrab keyboard")
