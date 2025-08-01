import json

from gi.repository import Gdk

import config.data as data
from fabric.hyprland.widgets import get_hyprland_connection
from fabric.widgets.box import Box
from fabric.widgets.eventbox import EventBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from utils.icon_resolver import IconResolver
from widgets.wayland import WaylandWindow as Window


class ApplicationSwitcher(Window):
    def __init__(self, **kwargs):
        super().__init__(
            name="application-switcher",
            layer="top",
            anchor="center",
            exclusivity="auto",
            keyboard_mode="exclusive",
            **kwargs,
        )

        self.conn = get_hyprland_connection()
        self.icon_resolver = IconResolver()
        self.windows = []
        self.current_index = 0
        self.tab_pressed = False
        self.items_per_row = data.WINDOW_SWITCHER_ITEMS_PER_ROW
        self.icon_size = 64

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
            orientation="v",
            spacing=0,
            h_align="center",
            v_align="center",
        )
        container.add(self.view)
        self.connect("key-press-event", self.on_key_press)
        self.connect("key-release-event", self.on_key_release)
        self.show_all()
        self.hide()

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

    def _is_special_workspace(self, client):
        """Check if a client is in a special workspace"""
        if "workspace" not in client:
            return False

        workspace = client["workspace"]
        if "name" in workspace:
            workspace_name = str(workspace["name"])
            # Special workspaces typically start with "special:" or have negative IDs
            if workspace_name.startswith("special:"):
                return True

        if "id" in workspace:
            workspace_id = workspace["id"]
            # Special workspaces have negative IDs
            if workspace_id < 0:
                return True

        return False

    def update_windows(self) -> None:
        for child in self.view.get_children():
            self.view.remove(child)

        try:
            clients_data = self.conn.send_command("j/clients").reply
            if not clients_data:
                return
            clients = json.loads(clients_data.decode("utf-8"))

            # Filter out hidden windows and optionally special workspace windows
            filtered_windows = []
            for c in clients:
                if c.get("hidden", False):
                    continue
                # Skip clients in special workspaces if the setting is enabled
                if (
                    data.DOCK_HIDE_SPECIAL_WORKSPACE_APPS
                    and self._is_special_workspace(c)
                ):
                    continue
                filtered_windows.append(c)

            self.windows = filtered_windows

            active_data = self.conn.send_command("j/activewindow").reply
            active_window = (
                json.loads(active_data.decode("utf-8")) if active_data else None
            )

            self.current_index = 0
            if active_window:
                for i, window in enumerate(self.windows):
                    if window.get("address") == active_window.get("address"):
                        self.current_index = i
                        break

            current_row = Box(
                name="window-row",
                orientation="h",
                spacing=12,
                h_align="center",
                v_align="center",
            )
            self.view.add(current_row)

            for i, window in enumerate(self.windows):
                class_name = window.get("class", "").lower()
                title = window.get("title", "")

                icon_img = self.icon_resolver.get_icon_pixbuf(
                    class_name, self.icon_size
                )
                if not icon_img:
                    icon_img = self.icon_resolver.get_icon_pixbuf(
                        "application-x-executable-symbolic", self.icon_size
                    )

                button_content = Box(
                    name="switcher-button",
                    orientation="v",
                    spacing=4,
                    h_align="center",
                    v_align="center",
                    children=[
                        Image(pixbuf=icon_img),
                        Label(
                            label=title[:15] + "..." if len(title) > 15 else title,
                            h_align="center",
                            v_align="center",
                            max_width_chars=15,
                            ellipsize="end",
                        ),
                    ],
                )

                event_box = EventBox(
                    name="window-button",
                    style_classes=["active"] if i == self.current_index else None,
                    child=button_content,
                )
                current_row.add(event_box)

                if (i + 1) % self.items_per_row == 0 and i + 1 < len(self.windows):
                    current_row = Box(
                        name="window-row",
                        orientation="h",
                        spacing=12,
                        h_align="center",
                        v_align="center",
                    )
                    self.view.add(current_row)

            self.view.show_all()
            self.update_selection()
        except Exception as e:
            print(f"Failed to update windows: {e}")

    def on_key_press(self, widget, event):
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

    def on_key_release(self, widget, event):
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
        for row in self.view.get_children():
            for i, child in enumerate(row.get_children()):
                index = self.view.get_children().index(row) * self.items_per_row + i
                if index == self.current_index:
                    child.add_style_class("active")
                else:
                    child.remove_style_class("active")

    def activate_selected(self):
        if not self.windows or self.current_index >= len(self.windows):
            return

        window = self.windows[self.current_index]
        address = window.get("address")
        if address:
            try:
                command = f"/dispatch focuswindow address:{address}"
                self.conn.send_command(command)
            except Exception as e:
                print(f"Failed to focus window: {e}")

    def grab_keyboard(self):
        try:
            display = Gdk.Display.get_default()
            seat = display.get_default_seat()
            window = self.get_window()
            seat.grab(window, Gdk.SeatCapabilities.KEYBOARD, False, None, None, None)
        except Exception as e:
            print(f"Failed to grab keyboard: {e}")

    def ungrab_keyboard(self):
        try:
            display = Gdk.Display.get_default()
            seat = display.get_default_seat()
            seat.ungrab()
        except Exception as e:
            print(f"Failed to ungrab keyboard: {e}")
