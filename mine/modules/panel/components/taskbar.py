import json

from fabric.hyprland.service import Hyprland, HyprlandEvent
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image

import config.data as data
from services import has_config_changed, on_config_change
from utils.functions import is_special_workspace_id
from utils.icon_resolver import IconResolver


class TaskBar(Box):
    def __init__(self, **kwargs):
        super().__init__(
            orientation="h",
            spacing=6,
            name="taskbar",
            **kwargs,
        )

        self.icon_resolver = IconResolver()
        self._clients = {}
        self._buttons = {}
        self._workspace_monitor_source_id = None
        self._visibility_callback = None
        self._hyprland_connection = Hyprland()

        # Connect to Hyprland events
        self._hyprland_connection.connect("event::openwindow", self._on_open_window)
        self._hyprland_connection.connect("event::closewindow", self._on_close_window)
        self._hyprland_connection.connect(
            "event::activewindowv2", self._on_active_window
        )
        self._hyprland_connection.connect("event::movewindow", self._on_move_window)
        self._hyprland_connection.connect(
            "event::workspacev2", self._on_workspace_changed
        )

        on_config_change(self._on_config_change)
        self._load_config()
        self._init_clients()
        self._update_visibility()

    def _init_clients(self):
        """Initialize clients from current Hyprland state"""
        res = self._hyprland_connection.send_command("j/clients")
        if not res or not res.reply:
            return

        try:
            clients = json.loads(res.reply.decode("utf-8"))
            active_res = self._hyprland_connection.send_command("j/activewindow")
            active_address = None
            if active_res and active_res.reply:
                active_window = json.loads(active_res.reply.decode("utf-8"))
                active_address = active_window.get("address")

            for client_data in clients:
                address = client_data.get("address")
                if address:
                    is_active = address == active_address
                    self._add_client(address, client_data, is_active)
        except Exception as e:
            print(f"Error initializing taskbar clients: {e}")

    def _on_open_window(self, _, event):
        if len(event.data) >= 1:
            address = "0x" + event.data[0]
            self._update_client_data(address)

    def _on_close_window(self, _, event):
        if len(event.data) >= 1:
            address = "0x" + event.data[0]
            self._remove_client(address)

    def _on_active_window(self, _, event):
        active_address = (
            ("0x" + event.data[0]) if event.data and event.data[0] else None
        )

        for key, btn_data in self._buttons.items():
            button = btn_data["button"]
            if self._group_apps:
                # Grouped mode: active if any address in group is active
                is_active = active_address in btn_data["addresses"]
            else:
                # Normal mode: active if address matches key
                is_active = key == active_address

            if is_active:
                button.add_style_class("active")
            else:
                button.remove_style_class("active")

    def _on_move_window(self, _, event):
        if len(event.data) >= 1:
            address = "0x" + event.data[0]
            self._update_client_data(address)

    def _update_client_data(self, address):
        res = self._hyprland_connection.send_command("j/clients")
        if not res or not res.reply:
            return

        try:
            clients = json.loads(res.reply.decode("utf-8"))
            for client_data in clients:
                if client_data.get("address") == address:
                    if address in self._clients:
                        self._clients[address] = client_data
                        self._update_client_button_properties(address)
                    else:
                        self._add_client(address, client_data)
                    break
        except Exception as e:
            print(f"Error updating client data: {e}")

    def _get_button_key(self, client_data):
        if self._group_apps:
            return client_data.get("class", "unknown")
        return client_data.get("address")

    def _add_client(self, address, client_data, is_active=False):
        self._clients[address] = client_data
        key = self._get_button_key(client_data)

        if key in self._buttons:
            # Button already exists (only in grouping mode)
            if address not in self._buttons[key]["addresses"]:
                self._buttons[key]["addresses"].append(address)
            if is_active:
                self._buttons[key]["button"].add_style_class("active")
        else:
            # Create new button
            client_image = Image()

            def on_click(k=key):
                addresses = self._buttons[k]["addresses"]
                if not addresses:
                    return

                # Cycle behavior: focus the next one if the current active is in this group
                active_res = self._hyprland_connection.send_command("j/activewindow")
                current_active = None
                if active_res and active_res.reply:
                    active_window = json.loads(active_res.reply.decode("utf-8"))
                    current_active = active_window.get("address")

                target_address = addresses[0]
                if current_active in addresses:
                    idx = (addresses.index(current_active) + 1) % len(addresses)
                    target_address = addresses[idx]

                self._hyprland_connection.send_command(
                    f"/dispatch focuswindow address:{target_address}"
                )

            client_button = Button(
                image=client_image, on_button_press_event=lambda *_: on_click()
            )
            if is_active:
                client_button.add_style_class("active")

            self._buttons[key] = {
                "button": client_button,
                "image": client_image,
                "addresses": [address],
            }

            self._update_button_visuals(key)

        self._update_visibility()

    def _remove_client(self, address):
        if address not in self._clients:
            return

        client_data = self._clients[address]
        key = self._get_button_key(client_data)

        if key in self._buttons:
            if address in self._buttons[key]["addresses"]:
                self._buttons[key]["addresses"].remove(address)

            if not self._buttons[key]["addresses"]:
                # Last window of the group/address closed
                button = self._buttons[key]["button"]
                if button.get_parent() == self:
                    self.remove(button)
                button.destroy()
                del self._buttons[key]
            else:
                # Update visuals (e.g. tooltip)
                self._update_button_visuals(key)

        del self._clients[address]
        self._update_visibility()

    def _update_client_button_properties(self, address):
        """Update properties of the button associated with this address"""
        if address not in self._clients:
            return
        key = self._get_button_key(self._clients[address])
        self._update_button_visuals(key)

    def _update_button_visuals(self, key):
        if key not in self._buttons:
            return

        btn_data = self._buttons[key]
        button = btn_data["button"]
        image = btn_data["image"]
        addresses = btn_data["addresses"]

        if not addresses:
            return

        # Use data from the first address for the icon/title
        first_address = addresses[0]
        client_data = self._clients.get(first_address, {})

        app_id = client_data.get("class", "")
        title = client_data.get("title", "")

        if self._group_apps and len(addresses) > 1:
            title = f"{title} ({len(addresses)})"

        image.set_from_pixbuf(
            self.icon_resolver.get_icon_pixbuf(app_id, self._icon_size)
        )
        button.set_tooltip_text(title)

        # Also re-check visibility
        self._update_button_visibility(key)

    def _on_workspace_changed(self, _, event: HyprlandEvent):
        for key in list(self._buttons.keys()):
            self._update_button_visibility(key)
        self._update_visibility()

    def _update_button_visibility(self, key):
        if key not in self._buttons:
            return

        btn_data = self._buttons[key]
        button = btn_data["button"]
        addresses = btn_data["addresses"]

        # A grouped button should be visible if ANY of its windows should be visible
        should_be_visible = False
        for address in addresses:
            client_data = self._clients.get(address)
            if not client_data:
                continue

            workspace_id = self._get_workspace_id(client_data)
            if workspace_id is not None:
                is_special = is_special_workspace_id(workspace_id)
                if not (self._hide_special and is_special):
                    should_be_visible = True
                    break

        button_present = button.get_parent() is not None
        if should_be_visible and not button_present:
            self.add(button)
        elif not should_be_visible and button_present:
            self.remove(button)

    def _get_workspace_id(self, client_data):
        workspace_data = client_data.get("workspace", {})
        if isinstance(workspace_data, dict):
            return workspace_data.get("id")
        elif isinstance(workspace_data, (int, str)):
            return workspace_data
        return None

    def _load_config(self):
        self._icon_size = data.DATA()["taskbar_icon_size"]
        self._hide_special = data.DATA()["taskbar_hide_special"]
        self._group_apps = data.DATA()["taskbar_group_apps"]

    def _on_config_change(self, new_config, old_config):
        config_paths = [
            "panel.taskbar.icon_size",
            "panel.taskbar.hide_empty",
            "panel.taskbar.hide_special",
            "panel.taskbar.group_apps",
        ]

        config_changed = any(
            has_config_changed(old_config, new_config, path) for path in config_paths
        )

        if config_changed:
            self._load_config()
            # Force full rebuild of buttons on mode change
            self._rebuild_all()

    def _rebuild_all(self):
        """Clear all and re-initialize based on current config"""
        for child in self.get_children():
            self.remove(child)
        for btn_data in self._buttons.values():
            btn_data["button"].destroy()

        self._buttons = {}
        current_clients = self._clients.copy()
        self._clients = {}

        for address, client_data in current_clients.items():
            active_res = self._hyprland_connection.send_command("j/activewindow")
            is_active = False
            if active_res and active_res.reply:
                active_window = json.loads(active_res.reply.decode("utf-8"))
                is_active = address == active_window.get("address")

            self._add_client(address, client_data, is_active)

        self._update_visibility()

    def force_update_for_workspace_change(self):
        self._on_workspace_changed(None, None)

    def set_visibility_callback(self, callback):
        self._visibility_callback = callback

    def _update_visibility(self):
        has_visible_children = any(child.get_visible() for child in self.get_children())
        self.set_visible(has_visible_children)

        if self._visibility_callback:
            self._visibility_callback()
