from typing import Dict, Tuple

from fabric.utils import Gdk, GdkPixbuf, logger
from fabric.widgets.box import Box
from fabric.widgets.eventbox import EventBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.wayland import WaylandWindow as Window

from services.config import config, on_config_change
from services.modus import get_clients, get_active_window, focus_window
from utils.functions import is_special_workspace
from utils.icon_resolver import IconResolver


class ApplicationSwitcher(Window):
    def __init__(self, **kwargs):
        super().__init__(
            name="application-switcher",
            title="modus-switcher",
            layer="top",
            anchor="center",
            exclusivity="auto",
            keyboard_mode="exclusive",
            visible=False,
            **kwargs,
        )

        self.icon_resolver = IconResolver()
        self.windows = []
        self.current_index = 0
        self.tab_pressed = False
        self.icon_size = 96
        self._pixbuf_cache: Dict[Tuple[str, int], GdkPixbuf.Pixbuf] = {}

        on_config_change(self._on_config_changed)

        container = Box(
            name="application-switcher-container",
            orientation="v",
            h_align="center",
            v_align="center",
            expand=True,
        )
        self.add(container)

        self.view = Box(
            name="application-switcher-view",
            orientation="h",
            spacing=16,
            h_align="center",
            v_align="center",
        )
        container.add(self.view)

        self.selection_label = Label(
            name="switcher-selection-label",
            label="",
            h_align="center",
            v_align="center",
            style_classes=["switcher-selection-label"],
        )
        container.add(self.selection_label)

        self.workspace_label = Label(
            name="switcher-workspace-label",
            label="",
            h_align="center",
            v_align="center",
            style_classes=["switcher-workspace-label"],
        )
        container.add(self.workspace_label)

        self.connect("key-press-event", self.on_key_press)
        self.connect("key-release-event", self.on_key_release)

        self.show_all()
        self.hide()

    @property
    def items_per_row(self):
        return config().get("window_switcher_items_per_row", 10)

    def _on_config_changed(self, new_config, old_config):
        if config().has_changed(
            "hide_special_workspace", old_config
        ) or config().has_changed("window_switcher_items_per_row", old_config):
            if self.get_visible():
                self.update_windows()

    def show_switcher(self) -> None:
        self.update_windows()
        if not self.windows:
            return

        self.show()
        self.grab_keyboard()
        self.tab_pressed = False

    def hide_switcher(self) -> None:
        self.hide()
        self.ungrab_keyboard()

    def create_icon_for_window(self, window):
        class_name = window.get("class", "").lower()
        key = (class_name, self.icon_size)
        if key not in self._pixbuf_cache:
            icon_img = self.icon_resolver.get_icon_pixbuf(class_name, self.icon_size)
            if not icon_img:
                icon_img = self.icon_resolver.get_icon_pixbuf(
                    "application-x-executable-symbolic", self.icon_size
                )
            if icon_img:
                self._pixbuf_cache[key] = icon_img
        icon_img = self._pixbuf_cache.get(key)
        icon_image = Image()
        if icon_img:
            icon_image.set_from_pixbuf(icon_img)
        return icon_image

    def _is_special_workspace(self, client):
        return is_special_workspace(client)

    def update_windows(self) -> None:
        for child in self.view.get_children():
            child.destroy()

        try:
            clients = get_clients()
            if not clients:
                return

            hide_special = config().get("hide_special_workspace", True)

            filtered_windows = []
            for c in clients:
                if c.get("hidden", False):
                    continue
                if hide_special and self._is_special_workspace(c):
                    continue
                filtered_windows.append(c)

            self.windows = filtered_windows

            active_window = get_active_window()

            self.current_index = 0
            if active_window:
                for i, window in enumerate(self.windows):
                    if window.get("address") == active_window.get("address"):
                        self.current_index = i
                        break

            rows_box = Box(orientation="v", spacing=16)
            self.view.add(rows_box)

            current_row = None
            items_per_row = self.items_per_row

            for i, window in enumerate(self.windows):
                if i % items_per_row == 0:
                    current_row = Box(
                        name="window-row",
                        orientation="h",
                        spacing=16,
                        h_align="center",
                        v_align="center",
                    )
                    rows_box.add(current_row)

                icon_image = self.create_icon_for_window(window)

                button_content = Box(
                    name="switcher-button",
                    orientation="v",
                    h_align="center",
                    v_align="center",
                    children=[
                        Box(
                            name="switcher-icon-box",
                            style_classes=["window-basic", "sleek-border"],
                            children=[icon_image],
                            h_align="center",
                            v_align="center",
                        ),
                    ],
                )

                event_box = EventBox(
                    name="window-button",
                    style_classes=["active"] if i == self.current_index else None,
                    child=button_content,
                    events=["button-press-event"],
                )
                event_box.connect(
                    "button-press-event", lambda w, e, idx=i: self._on_item_clicked(idx)
                )
                current_row.add(event_box)

            self.view.show_all()
            self.update_selection()
        except Exception as e:
            logger.error(f"Failed to update windows: {e}")

    def on_key_press(self, _, event):
        keyval = event.keyval
        state = event.state
        alt_pressed = bool(state & Gdk.ModifierType.MOD1_MASK)

        if not self.windows:
            return False

        if keyval == Gdk.KEY_Escape:
            self.hide_switcher()
            return True

        if keyval == Gdk.KEY_Tab:
            if not self.tab_pressed or alt_pressed:
                self.current_index = (self.current_index + 1) % len(self.windows)
                self.update_selection()
                self.tab_pressed = True
            return True

        if keyval == Gdk.KEY_ISO_Left_Tab or (
            keyval == Gdk.KEY_Tab and (state & Gdk.ModifierType.SHIFT_MASK)
        ):
            self.current_index = (self.current_index - 1) % len(self.windows)
            self.update_selection()
            return True

        if keyval == Gdk.KEY_Return:
            self.activate_selected()
            self.hide_switcher()
            return True

        if keyval == Gdk.KEY_Right or keyval == Gdk.KEY_l:
            self.current_index = (self.current_index + 1) % len(self.windows)
            self.update_selection()
            return True

        if keyval == Gdk.KEY_Left or keyval == Gdk.KEY_h:
            self.current_index = (self.current_index - 1) % len(self.windows)
            self.update_selection()
            return True

        if keyval == Gdk.KEY_Down:
            next_index = self.current_index + self.items_per_row
            if next_index < len(self.windows):
                self.current_index = next_index
                self.update_selection()
            return True

        if keyval == Gdk.KEY_Up:
            next_index = self.current_index - self.items_per_row
            if next_index >= 0:
                self.current_index = next_index
                self.update_selection()
            return True

        return False

    def on_key_release(self, _, event):
        keyval = event.keyval

        if keyval in (Gdk.KEY_Alt_L, Gdk.KEY_Alt_R):
            self.activate_selected()
            self.hide_switcher()
            return True

        if keyval == Gdk.KEY_Tab:
            self.tab_pressed = False
            return True

        return False

    def update_selection(self):
        all_buttons = []
        rows_box = self.view.get_children()[0] if self.view.get_children() else None
        if rows_box:
            for row in rows_box.get_children():
                all_buttons.extend(row.get_children())

        for i, child in enumerate(all_buttons):
            if i == self.current_index:
                child.add_style_class("active")
                current_window = self.windows[self.current_index]
                app_class = current_window.get("class", "Unknown")
                if app_class.islower():
                    app_class = app_class.capitalize()
                self.selection_label.set_label(app_class)

                workspace = current_window.get("workspace", {})
                workspace_name = workspace.get("name", "Unknown")
                self.workspace_label.set_label(f"Workspace {workspace_name}")
            else:
                child.remove_style_class("active")

    def activate_selected(self):
        if not self.windows or self.current_index >= len(self.windows):
            return

        window = self.windows[self.current_index]
        address = window.get("address")
        if address:
            focus_window(address)

    def _on_item_clicked(self, index):
        self.current_index = index
        self.update_selection()
        self.activate_selected()
        self.hide_switcher()

    def grab_keyboard(self):
        try:
            display = Gdk.Display.get_default()
            seat = display.get_default_seat()
            window = self.get_window()
            seat.grab(window, Gdk.SeatCapabilities.KEYBOARD, False, None, None, None)
        except Exception as e:
            logger.error(f"Failed to grab keyboard: {e}")

    def ungrab_keyboard(self):
        try:
            display = Gdk.Display.get_default()
            seat = display.get_default_seat()
            seat.ungrab()
        except Exception as e:
            logger.error(f"Failed to ungrab keyboard: {e}")
