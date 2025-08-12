from gi.repository import GLib, Gtk
import json
import os
import re
import subprocess

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.eventbox import EventBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.overlay import Overlay
from fabric.widgets.revealer import Revealer
from fabric.widgets.separator import Separator
from widgets.wayland import WaylandWindow as Window
from loguru import logger

from utils.icon_resolver import IconResolver
from utils.occlusion import check_occlusion
from fabric.utils.helpers import get_relative_path, get_desktop_applications
from services.modus import modus_service
from utils.functions import read_json_file, write_json_file
import config.data as data

# Pinned apps file
PINNED_APPS_FILE = get_relative_path("../config/assets/dock.json")


class AppBar(Box):
    def __init__(self, parent: Window):
        self.client_buttons = {}  # For running app instances
        self.pinned_buttons = {}  # For pinned apps
        self._parent = parent

        # Set orientation based on dock position
        orientation = "vertical" if data.DOCK_POSITION in ["Left", "Right"] else "horizontal"
        
        super().__init__(
            spacing=10,
            name="dock",
            orientation=orientation,
            children=[],
        )
        self.icon_resolver = IconResolver()
        self._hyprland_connection = modus_service._hyprland_connection

        # Initialize GTK menu
        self.menu = Gtk.Menu()

        self.pinned_apps = read_json_file(PINNED_APPS_FILE) or []
        self.pinned_apps_container = Box(name="pinned-apps-container")
        self.add(self.pinned_apps_container)

        self.separator = Separator(name="dock-separator")
        self.add(self.separator)

        self.running_apps_container = Box(name="running-apps-container")
        self.add(self.running_apps_container)

        self._populate_pinned_apps()
        self.setup_app_monitoring()

    def setup_app_monitoring(self):
        def update_running_apps():
            try:
                self.update_dock_apps()
            except Exception as e:
                logger.error(f"[AppBar] Error updating apps: {e}")
            return True

        GLib.timeout_add(1000, update_running_apps)
        GLib.idle_add(self.update_dock_apps)

    def _populate_pinned_apps(self):
        for child in self.pinned_apps_container.get_children():
            self.pinned_apps_container.remove(child)

        self.pinned_buttons = {}

        try:
            desktop_apps = get_desktop_applications(include_hidden=False)
        except Exception:
            desktop_apps = []

        for app_data in self.pinned_apps:
            self._create_pinned_button(app_data, desktop_apps)

    def _create_pinned_button(self, app_data, desktop_apps):
        if isinstance(app_data, dict):
            app_identifier = app_data.get("name", "") or app_data.get(
                "window_class", ""
            )
            display_name = app_data.get("display_name", app_identifier)
            app = self._find_desktop_app_from_data(app_data, desktop_apps)

            if app:
                icon_pixbuf = app.get_icon_pixbuf(data.DOCK_ICON_SIZE)
            else:
                icon_name = app_data.get("window_class", "") or app_data.get("name", "")
                icon_pixbuf = self.icon_resolver.get_icon_pixbuf(
                    icon_name, data.DOCK_ICON_SIZE
                )
        else:
            app_identifier = app_data
            app = self._find_desktop_app_by_id(app_data, desktop_apps)
            if not app:
                return

            display_name = app.display_name or app.name
            icon_pixbuf = app.get_icon_pixbuf(data.DOCK_ICON_SIZE)

        pinned_image = Image(pixbuf=icon_pixbuf)

        icon_container = Box(
            name="dock-icon",
            orientation="vertical",
            h_align="center",
            children=[pinned_image],
        )

        overlay_container = Overlay(name="dock-app-overlay", child=icon_container)

        pinned_button = Button(
            name="dock-app-button",
            child=overlay_container,
            tooltip_text=display_name,
            on_button_press_event=lambda _, event: self._handle_pinned_app_click(
                event, app_data
            ),
        )

        self.pinned_buttons[app_identifier] = pinned_button
        self.pinned_apps_container.add(pinned_button)

    def _find_desktop_app_from_data(self, app_data: dict, desktop_apps):
        for app in desktop_apps:
            if (
                (
                    app_data.get("name")
                    and app.name
                    and app.name.lower() == app_data["name"].lower()
                )
                or (
                    app_data.get("window_class")
                    and hasattr(app, "window_class")
                    and app.window_class
                    and app.window_class.lower() == app_data["window_class"].lower()
                )
                or (
                    app_data.get("executable")
                    and app.executable
                    and (
                        app.executable.lower() == app_data["executable"].lower()
                        or os.path.basename(app.executable).lower()
                        == os.path.basename(app_data["executable"]).lower()
                    )
                )
            ):
                return app
        return None

    def _find_desktop_app_by_id(self, app_id: str, desktop_apps):
        for app in desktop_apps:
            if (
                (app.name and app.name.lower() == app_id.lower())
                or (app.display_name and app.display_name.lower() == app_id.lower())
                or (
                    hasattr(app, "window_class")
                    and app.window_class
                    and app.window_class.lower() == app_id.lower()
                )
                or (
                    app.executable
                    and (
                        app.executable.lower() == app_id.lower()
                        or os.path.basename(app.executable).lower() == app_id.lower()
                    )
                )
            ):
                return app
        return None

    def show_menu(self, app_id: str, client=None, instance_address=None):
        for item in self.menu.get_children():
            self.menu.remove(item)
            item.destroy()

        if client or instance_address:
            close_item = Gtk.MenuItem(label="Close")
            if instance_address:
                close_item.connect(
                    "activate", lambda *_: self._close_running_app(instance_address)
                )
            self.menu.add(close_item)

            if app_id:
                separator = Gtk.SeparatorMenuItem()
                self.menu.add(separator)

        if app_id:
            is_pinned = self._is_app_pinned(app_id)
            pin_item = Gtk.MenuItem(label="Unpin" if is_pinned else "Pin")

            if is_pinned:
                pin_item.connect("activate", lambda *_: self._unpin_app(app_id))
            else:
                pin_item.connect("activate", lambda *_: self._pin_app(app_id))

            self.menu.add(pin_item)

        self.menu.show_all()

    def _close_running_app(self, instance_address):
        try:
            self._hyprland_connection.send_command(
                f"dispatch closewindow address:{instance_address}"
            )
        except Exception as e:
            logger.error(f"[AppBar] Error closing window: {e}")

    def _handle_pinned_app_click(self, event, app_data):
        if event.button == 1:  # Left click - launch app
            self._launch_app_data(app_data)
        elif event.button == 2:  # Middle click - unpin app
            app_identifier = self._get_app_identifier(app_data)
            self._unpin_app(app_identifier)
        elif event.button == 3:  # Right click - show context menu
            app_identifier = self._get_app_identifier(app_data)
            self.show_menu(app_identifier)
            self.menu.popup_at_pointer(event)

    def _get_app_identifier(self, app_data):
        if isinstance(app_data, dict):
            return app_data.get("name", "") or app_data.get("window_class", "")
        return app_data

    def _launch_app_data(self, app_data):
        try:
            desktop_apps = get_desktop_applications(include_hidden=False)

            if isinstance(app_data, dict):
                app = self._find_desktop_app_from_data(app_data, desktop_apps)
                if app:
                    self._launch_app(app)
                else:
                    self._launch_app_from_data(app_data)
            else:
                app = self._find_desktop_app_by_id(app_data, desktop_apps)
                if app:
                    self._launch_app(app)
        except Exception as e:
            logger.error(f"[AppBar] Failed to launch app: {e}")

    def _launch_app(self, app):
        try:
            cleaned_command = re.sub(r"%\w+", "", app.command_line).strip()
            final_command = f"hyprctl dispatch exec 'uwsm app -- {cleaned_command}'"
            subprocess.Popen(final_command, shell=True)
        except Exception:
            try:
                app.launch()
            except Exception as fallback_error:
                logger.error(f"[AppBar] Failed to launch app: {fallback_error}")

    def _launch_app_from_data(self, app_data):
        try:
            command_line = app_data.get("command_line", "")
            if command_line:
                cleaned_command = re.sub(r"%\w+", "", command_line).strip()
                final_command = f"hyprctl dispatch exec 'uwsm app -- {cleaned_command}'"
                subprocess.Popen(final_command, shell=True)
            elif app_data.get("executable"):
                final_command = (
                    f"hyprctl dispatch exec 'uwsm app -- {app_data['executable']}'"
                )
                subprocess.Popen(final_command, shell=True)
            else:
                logger.error(
                    f"[AppBar] No command or executable found for app: {app_data}"
                )
        except Exception as e:
            logger.error(f"[AppBar] Failed to launch app from data: {e}")

    def _pin_app(self, app_class: str):
        if self._is_app_pinned(app_class):
            return False

        try:
            desktop_apps = get_desktop_applications(include_hidden=False)
            app = self._find_desktop_app_by_id(app_class, desktop_apps)

            if app:
                app_data = {
                    "name": app.name,
                    "display_name": app.display_name or app.name,
                    "window_class": getattr(app, "window_class", None) or app_class,
                    "executable": app.executable,
                    "command_line": app.command_line,
                }
            else:
                # Fallback: create minimal app data
                app_data = {
                    "name": app_class,
                    "display_name": app_class,
                    "window_class": app_class,
                    "executable": app_class,
                    "command_line": app_class,
                }

            self.pinned_apps.append(app_data)
        except Exception:
            self.pinned_apps.append(app_class)

        write_json_file(self.pinned_apps, PINNED_APPS_FILE)
        self._populate_pinned_apps()
        return True

    def _unpin_app(self, app_identifier: str):
        apps_to_remove = []

        for i, pinned_app in enumerate(self.pinned_apps):
            if self._matches_app_identifier(pinned_app, app_identifier):
                apps_to_remove.append(i)

        for i in reversed(apps_to_remove):
            self.pinned_apps.pop(i)

        if apps_to_remove:
            write_json_file(self.pinned_apps, PINNED_APPS_FILE)
            self._populate_pinned_apps()
            return True
        return False

    def _matches_app_identifier(self, pinned_app, app_identifier):
        if not app_identifier:
            return False

        if isinstance(pinned_app, dict):
            window_class = pinned_app.get("window_class") or ""
            name = pinned_app.get("name") or ""
            return (
                window_class.lower() == app_identifier.lower()
                or name.lower() == app_identifier.lower()
            )
        return (
            isinstance(pinned_app, str) and pinned_app.lower() == app_identifier.lower()
        )

    def get_clients(self):
        try:
            clients_data = self._hyprland_connection.send_command("j/clients").reply
            if not clients_data:
                return []
            return json.loads(clients_data.decode("utf-8"))
        except Exception as e:
            logger.error(f"[AppBar] Error getting clients: {e}")
            return []

    def get_focused_window(self):
        try:
            active_data = self._hyprland_connection.send_command("j/activewindow").reply
            if not active_data:
                return None
            return json.loads(active_data.decode("utf-8"))
        except Exception as e:
            logger.error(f"[AppBar] Error getting focused window: {e}")
            return None

    def update_dock_apps(self):
        clients = self.get_clients()
        focused_window = self.get_focused_window()
        focused_address = focused_window.get("address", "") if focused_window else ""

        current_instance_ids = set()

        for client in clients:
            if client.get("hidden", False):
                continue

            # Skip apps in special workspaces if configured to hide them
            if not self._should_show_app_instance(client):
                continue

            instance_address = client.get("address", "")
            if not instance_address:
                continue

            current_instance_ids.add(instance_address)
            app_class = client.get("class", "") or client.get("title", "unknown-app")

            if instance_address not in self.client_buttons:
                self.create_instance_button(instance_address, client, app_class)
            else:
                self.update_instance_button(instance_address, client, app_class)

            button = self.client_buttons[instance_address]
            if instance_address == focused_address:
                button.add_style_class("active")
            else:
                button.remove_style_class("active")

        self._update_pinned_apps_state(clients)
        self._update_separator_visibility()

        self._cleanup_removed_instances(current_instance_ids)

    def _update_pinned_apps_state(self, clients):
        running_app_classes = {
            client.get("class", "").lower() or client.get("title", "").lower()
            for client in clients
            if not client.get("hidden", False)
            and (client.get("class") or client.get("title"))
            and self._should_show_app_instance(client)
        }

        for app_identifier, button in self.pinned_buttons.items():
            if app_identifier.lower() in running_app_classes:
                button.add_style_class("instance")
            else:
                button.remove_style_class("instance")

    def _cleanup_removed_instances(self, current_instance_ids):
        buttons_to_remove = [
            instance_id
            for instance_id in self.client_buttons.keys()
            if instance_id not in current_instance_ids
        ]

        for instance_id in buttons_to_remove:
            button = self.client_buttons.pop(instance_id)
            self.running_apps_container.remove(button)

    def create_instance_button(self, instance_address, client, app_class):
        client_image = Image()

        try:
            desktop_apps = get_desktop_applications(include_hidden=False)
            desktop_app = self._find_desktop_app_by_id(app_class, desktop_apps)

            if desktop_app:
                pixbuf = desktop_app.get_icon_pixbuf(data.DOCK_ICON_SIZE)
            else:
                pixbuf = self.icon_resolver.get_icon_pixbuf(app_class, data.DOCK_ICON_SIZE)

            client_image.set_from_pixbuf(pixbuf)
        except Exception as e:
            logger.warning(f"[AppBar] Could not load icon for {app_class}: {e}")

        workspace_id = self._get_workspace_id(client)
        workspace_label = None
        if workspace_id is not None:
            workspace_label = Label(
                label=str(workspace_id),
                name="workspace-indicator",
                h_align="end",
                v_align="end",
            )

        image_overlay = Overlay(name="dock-image-overlay", child=client_image)
        if workspace_label:
            image_overlay.add_overlay(workspace_label)

        icon_container = Box(
            name="dock-icon",
            orientation="vertical",
            h_align="center",
            children=[image_overlay],
        )

        overlay_container = Overlay(name="dock-app-overlay", child=icon_container)

        tooltip_text = client.get("title", app_class)
        if tooltip_text != app_class:
            tooltip_text = f"{app_class}: {tooltip_text}"

        client_button = Button(
            name="dock-app-button",
            child=overlay_container,
            tooltip_text=tooltip_text,
            on_button_press_event=lambda widget, event: self.handle_instance_click(
                widget, event
            ),
        )

        client_button.instance_address = instance_address
        client_button.client_data = client
        client_button.app_class = app_class
        client_button.workspace_label = workspace_label

        self.client_buttons[instance_address] = client_button
        self.running_apps_container.add(client_button)

    def _get_workspace_id(self, client):
        workspace_data = client.get("workspace", {})
        if isinstance(workspace_data, dict):
            return workspace_data.get("id")
        elif isinstance(workspace_data, (int, str)):
            return workspace_data
        return None

    def _is_special_workspace_id(self, ws_id):
        """Check if a workspace ID represents a special workspace"""
        try:
            # Convert to int if it's a string
            workspace_id = int(ws_id)
            # Special workspaces have negative IDs
            return workspace_id < 0
        except (ValueError, TypeError):
            # If it's a string, check if it starts with "special:"
            if isinstance(ws_id, str) and ws_id.startswith("special:"):
                return True
            return False

    def _should_show_app_instance(self, client):
        """Determine if an app instance should be shown based on workspace and configuration"""
        if not data.DOCK_HIDE_SPECIAL_WORKSPACE_APPS:
            return True
            
        workspace_id = self._get_workspace_id(client)
        if workspace_id is None:
            return True
            
        return not self._is_special_workspace_id(workspace_id)

    def update_instance_button(self, instance_address, client, app_class):
        if instance_address not in self.client_buttons:
            return

        button = self.client_buttons[instance_address]
        button.client_data = client
        button.app_class = app_class

        tooltip_text = client.get("title", app_class)
        if tooltip_text != app_class:
            tooltip_text = f"{app_class}: {tooltip_text}"
        button.set_tooltip_text(tooltip_text)

        workspace_id = self._get_workspace_id(client)
        existing_label = getattr(button, "workspace_label", None)

        overlay_container = button.get_child()
        if isinstance(overlay_container, Overlay):
            icon_container = overlay_container.get_child()
            if hasattr(icon_container, "get_children"):
                children = icon_container.get_children()
                if children:
                    image_overlay = children[0]
                    if isinstance(image_overlay, Overlay):
                        # Remove existing workspace label
                        if existing_label and existing_label.get_parent():
                            image_overlay.remove_overlay(existing_label)

                        # Add new workspace label if needed
                        if workspace_id is not None:
                            new_label = Label(
                                label=str(workspace_id),
                                name="workspace-indicator",
                                h_align="end",
                                v_align="end",
                            )
                            image_overlay.add_overlay(new_label)
                            button.workspace_label = new_label
                        else:
                            button.workspace_label = None

    def handle_instance_click(self, button_widget, event):
        instance_address = getattr(button_widget, "instance_address", None)
        app_class = getattr(button_widget, "app_class", None)

        if event.button == 1:  # Left click - focus window
            if instance_address:
                try:
                    self._hyprland_connection.send_command(
                        f"dispatch focuswindow address:{instance_address}"
                    )
                except Exception as e:
                    logger.error(f"[AppBar] Error focusing window: {e}")

        elif event.button == 2:  # Middle click - pin/unpin app
            if app_class and not self._is_app_pinned(app_class):
                self._pin_app(app_class)

        elif event.button == 3:  # Right click - context menu
            if app_class:
                self.show_menu(app_class, instance_address=instance_address)
                self.menu.popup_at_pointer(event)

    def _is_app_pinned(self, app_class: str) -> bool:
        return any(
            self._matches_app_identifier(pinned_app, app_class)
            for pinned_app in self.pinned_apps
        )

    def _update_separator_visibility(self):
        has_pinned_apps = len(self.pinned_buttons) > 0
        has_running_apps = len(self.client_buttons) > 0
        self.separator.set_visible(has_pinned_apps and has_running_apps)


class Dock(Window):
    def __init__(self):
        if not data.DOCK_ENABLED:
            anchor = self._get_anchor_from_position()
            super().__init__(layer="top", anchor=anchor)
            self.children = Box()  # Empty dock if disabled
            return

        anchor = self._get_anchor_from_position()
        super().__init__(layer="top", anchor=anchor)

        self.app_bar = AppBar(self)
        
        transition_type = self._get_transition_type()
        
        self.revealer = Revealer(
            child=Box(children=[self.app_bar], style="padding: 20px 50px 5px 50px;"),
            transition_duration=500,
            transition_type=transition_type,
        )

        self.children = EventBox(
            events=["enter-notify", "leave-notify"],
            child=Box(style="min-height: 1px", children=self.revealer),
            on_enter_notify_event=lambda *_: self.on_hover_enter(),
            on_leave_notify_event=lambda *_: self.on_hover_leave(),
        )

        self.revealer.set_reveal_child(True)

        self.dock_height = 100
        self.is_hovered = False
        self.hide_timeout_id = None
        
        # Only setup occlusion monitoring if auto-hide is enabled
        if data.DOCK_AUTO_HIDE:
            self.setup_occlusion_monitoring()

    def on_hover_enter(self):
        self.is_hovered = True
        if self.hide_timeout_id:
            GLib.source_remove(self.hide_timeout_id)
            self.hide_timeout_id = None
        self.revealer.set_reveal_child(True)

    def on_hover_leave(self):
        self.is_hovered = False

    def _get_anchor_from_position(self):
        if data.DOCK_POSITION == "Left":
            return "left center"
        elif data.DOCK_POSITION == "Right":
            return "right center"
        else:  # Bottom (default)
            return "bottom center"

    def _get_transition_type(self):
        if data.DOCK_POSITION == "Left":
            return "slide-right"
        elif data.DOCK_POSITION == "Right":
            return "slide-left"
        else:  # Bottom (default)
            return "slide-up"

    def _get_occlusion_position(self):
        if data.DOCK_POSITION == "Left":
            return ("left", self.dock_height)
        elif data.DOCK_POSITION == "Right":
            return ("right", self.dock_height)
        else:  # Bottom (default)
            return ("bottom", self.dock_height)

    def setup_occlusion_monitoring(self):
        def check_dock_occlusion():
            try:
                if data.DOCK_ALWAYS_OCCLUDED:
                    is_occluded = True
                else:
                    occlusion_position = self._get_occlusion_position()
                    is_occluded = check_occlusion(occlusion_position)

                if (
                    is_occluded
                    and not self.is_hovered
                    and self.revealer.get_reveal_child()
                ):
                    self.revealer.set_reveal_child(False)
                elif not is_occluded and not self.revealer.get_reveal_child():
                    self.revealer.set_reveal_child(True)
            except Exception as e:
                logger.error(f"[Dock] Occlusion check error: {e}")

            return True

        GLib.timeout_add(250, check_dock_occlusion)
