import json

import gi
from gi.repository import Gdk, Glace

import config.data as data
from fabric.hyprland.widgets import get_hyprland_connection
from fabric.widgets.box import Box
from fabric.widgets.eventbox import EventBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from utils.icon_resolver import IconResolver
from widgets.wayland import WaylandWindow as Window

gi.require_version("Glace", "0.1")


class ApplicationSwitcher(Window):
    def __init__(self, **kwargs):
        super().__init__(
            name="application-switcher",
            title="modus-switcher",
            layer="top",
            anchor="center",
            exclusivity="auto",
            keyboard_mode="exclusive",
            visible=False,  # Start hidden until explicitly shown
            **kwargs,
        )

        self.conn = get_hyprland_connection()
        self.icon_resolver = IconResolver()
        self.windows = []
        self.current_index = 0
        self.tab_pressed = False
        self.items_per_row = data.WINDOW_SWITCHER_ITEMS_PER_ROW
        self.icon_size = 64

        # Initialize Glace manager for window previews
        self._manager = Glace.Manager()
        self.preview_size = [150, 100]  # Preview size for each window in switcher
        self.glace_clients = {}  # Map window addresses to Glace clients
        self.window_previews = {}  # Map window addresses to preview images

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
            spacing=12,
            h_align="center",
            v_align="center",
        )
        container.add(self.view)
        self.connect("key-press-event", self.on_key_press)
        self.connect("key-release-event", self.on_key_release)

        # Connect to Glace manager signals to track clients
        self._manager.connect("client-added", self._on_glace_client_added)
        self._manager.connect("client-removed", self._on_glace_client_removed)

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

    def _on_glace_client_added(self, _, client):
        """Handle when a Glace client is added"""
        try:
            # Map the client by its window address for later lookup
            # We'll need to match this with Hyprland window data
            client_id = client.get_id()
            self.glace_clients[client_id] = client
        except Exception as e:
            print(f"Error adding Glace client: {e}")

    def _on_glace_client_removed(self, _, client):
        """Handle when a Glace client is removed"""
        try:
            client_id = client.get_id()
            if client_id in self.glace_clients:
                del self.glace_clients[client_id]
        except Exception as e:
            print(f"Error removing Glace client: {e}")

    def _find_glace_client_for_window(self, window):
        """Find the corresponding Glace client for a Hyprland window"""
        try:
            window_class = window.get("class", "").lower()
            window_title = window.get("title", "")

            # Try to match by app_id/class and title
            for _, client in self.glace_clients.items():
                try:
                    client_app_id = client.get_app_id()
                    client_title = client.get_title()

                    if (client_app_id and client_app_id.lower() == window_class and
                        client_title and client_title == window_title):
                        return client
                except Exception:
                    continue

            # Fallback: try to match by class only
            for _, client in self.glace_clients.items():
                try:
                    client_app_id = client.get_app_id()
                    if client_app_id and client_app_id.lower() == window_class:
                        return client
                except Exception:
                    continue

        except Exception as e:
            print(f"Error finding Glace client: {e}")

        return None

    def create_preview_for_window(self, window):
        """Create a preview image for a specific window"""
        glace_client = self._find_glace_client_for_window(window)

        # Create a placeholder image first
        preview_image = Image()

        if glace_client:
            def capture_callback(pbuf, _):
                try:
                    scaled_pixbuf = pbuf.scale_simple(
                        self.preview_size[0],
                        self.preview_size[1],
                        2  # GdkPixbuf.InterpType.BILINEAR
                    )
                    preview_image.set_from_pixbuf(scaled_pixbuf)
                except Exception as e:
                    print(f"Error setting preview image: {e}")

            try:
                self._manager.capture_client(
                    client=glace_client,
                    overlay_cursor=False,
                    callback=capture_callback,
                    user_data=None,
                )
            except Exception as e:
                print(f"Error capturing client preview: {e}")
                # Fallback to icon if preview fails
                self._set_fallback_icon(preview_image, window)
        else:
            # Use icon as fallback if no Glace client found
            self._set_fallback_icon(preview_image, window)

        return preview_image

    def _set_fallback_icon(self, image_widget, window):
        """Set a fallback icon when preview is not available"""
        class_name = window.get("class", "").lower()
        icon_img = self.icon_resolver.get_icon_pixbuf(class_name, self.icon_size)
        if not icon_img:
            icon_img = self.icon_resolver.get_icon_pixbuf(
                "application-x-executable-symbolic", self.icon_size
            )
        image_widget.set_from_pixbuf(icon_img)

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
                title = window.get("title", "")

                # Create preview image for this window
                preview_image = self.create_preview_for_window(window)

                button_content = Box(
                    name="switcher-button",
                    orientation="v",
                    spacing=4,
                    h_align="center",
                    v_align="center",
                    children=[
                        Box(
                            name="switcher-preview-box",
                            style_classes=["window-basic", "sleek-border"],
                            children=[preview_image],
                            h_align="center",
                            v_align="center",
                        ),
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
