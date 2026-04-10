import json
import subprocess

from fabric.utils import (
    GLib,
    Gtk,
    get_desktop_applications,
    get_relative_path,
    logger,
    os,
    random,
    re,
)
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.eventbox import EventBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.overlay import Overlay
from fabric.widgets.revealer import Revealer
from fabric.widgets.wayland import WaylandWindow as Window

import shared.data as data
from services.modus import modus_service
from utils.functions import (
    clear_children,
    is_special_workspace_id,
    read_json_file,
    write_json_file,
)
from utils.icon_resolver import IconResolver
from utils.occlusion import check_occlusion

# Pinned apps file
PINNED_APPS_FILE = get_relative_path("../../config/dock.json")


class AppBar(Box):
    def __init__(self, parent: Window):
        self.client_buttons = {}  # For running app instances
        self.pinned_buttons = {}  # For pinned apps
        # Position tracking for hover effects
        self.running_items_pos = []
        self.pinned_items_pos = []
        self._parent = parent

        # Set orientation based on dock position
        orientation = (
            "vertical" if data.DOCK_POSITION in ["Left", "Right"] else "horizontal"
        )

        super().__init__(
            spacing=0,
            name="dock",
            orientation=orientation,
            children=[],
        )
        self.icon_resolver = IconResolver()
        self._hyprland_connection = modus_service._hyprland_connection

        # Initialize GTK menu
        self.menu = Gtk.Menu()

        self.pinned_apps = read_json_file(PINNED_APPS_FILE) or []
        self.pinned_apps_container = Box()
        self.add(self.pinned_apps_container)

        self.separator = Box(
            v_align="center", style_classes=["hidden", "dock_separator"]
        )
        self.add(self.separator)

        self.running_apps_container = Box(name="dock_container")
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

        GLib.timeout_add(250, update_running_apps)
        GLib.idle_add(self.update_dock_apps)

    def _populate_pinned_apps(self):
        clear_children(self.pinned_apps_container)

        self.pinned_buttons = {}
        self.pinned_items_pos = []

        try:
            desktop_apps = get_desktop_applications(include_hidden=False)
        except Exception:
            desktop_apps = []

        for app_data in self.pinned_apps:
            self._create_pinned_button(app_data, desktop_apps)

        # Add trash icon at the end of pinned apps
        self._create_trash_button()

    def _create_pinned_button(self, app_data, desktop_apps):
        app = self._find_desktop_app(app_data, desktop_apps)
        app_identifier = self._get_app_identifier(app_data)
        display_name = (
            app.display_name
            if app
            else (
                app_data.get("display_name", app_identifier)
                if isinstance(app_data, dict)
                else app_identifier
            )
        )

        icon_pixbuf = self._get_app_icon(app_data, app)

        main_container = Box(
            name="dock_item_main_container",
            orientation="v",
            children=[Image(name="dock_item_icon", pixbuf=icon_pixbuf)],
        )

        pinned_button = Button(
            name="dock_item",
            child=main_container,
            tooltip_text=display_name,
            on_button_press_event=lambda _, event: self._handle_pinned_app_click(
                event, app_data
            ),
            on_enter_notify_event=lambda *_: self._set_item_hover_state(
                pinned_button, True, pinned=True
            ),
            on_leave_notify_event=lambda *_: self._set_item_hover_state(
                pinned_button, False, pinned=True
            ),
        )

        pinned_button.add_style_class("shown")

        self.pinned_buttons[app_identifier] = pinned_button
        self.pinned_apps_container.add(pinned_button)
        self.pinned_items_pos.append(pinned_button)

    def _get_app_icon(self, app_data, app=None):
        if app:
            return app.get_icon_pixbuf(data.DOCK_ICON_SIZE)

        icon_name = ""
        if isinstance(app_data, dict):
            icon_name = app_data.get("window_class") or app_data.get("name")
        elif isinstance(app_data, str):
            icon_name = app_data

        return self.icon_resolver.get_icon_pixbuf(
            icon_name or "application-x-executable", data.DOCK_ICON_SIZE
        )

    def _create_trash_button(self):
        """Create a trash button that opens the trash in file manager"""
        trash_icon_pixbuf = self.icon_resolver.get_icon_pixbuf(
            "user-trash", data.DOCK_ICON_SIZE
        )

        main_container = Box(
            name="dock_item_main_container",
            orientation="v",
            children=[Image(name="dock_item_icon", pixbuf=trash_icon_pixbuf)],
        )

        trash_button = Button(
            name="dock_item",
            child=main_container,
            tooltip_text="Trash",
            on_button_press_event=lambda _, event: self._handle_trash_click(event),
            on_enter_notify_event=lambda *_: self._set_item_hover_state(
                trash_button, True, pinned=True
            ),
            on_leave_notify_event=lambda *_: self._set_item_hover_state(
                trash_button, False, pinned=True
            ),
        )

        trash_button.add_style_class("shown")
        trash_button.is_trash = True

        self.pinned_buttons["trash"] = trash_button
        self.pinned_apps_container.add(trash_button)
        self.pinned_items_pos.append(trash_button)

    def _find_desktop_app(self, app_info, desktop_apps):
        """Find a desktop app from either a string ID or a data dictionary"""
        if not app_info:
            return None

        # Extract normalized search terms
        search_terms = []
        if isinstance(app_info, dict):
            search_terms = [
                app_info.get("window_class"),
                app_info.get("name"),
                app_info.get("executable"),
            ]
        else:
            search_terms = [app_info]

        search_terms = [s.lower() for s in search_terms if s and isinstance(s, str)]
        if not search_terms:
            return None

        # Handle Reverse DNS or decorated names (e.g., org.gnome.Nautilus, float_kitty)
        expanded_terms = list(search_terms)
        for term in search_terms:
            # Handle dots (Reverse DNS)
            if "." in term:
                parts = term.split(".")
                if parts[-1] and parts[-1] not in expanded_terms:
                    expanded_terms.append(parts[-1])

            # Handle underscores and hyphens (decorated names)
            for sep in ["_", "-"]:
                if sep in term:
                    for part in term.split(sep):
                        if len(part) > 2 and part not in expanded_terms:
                            expanded_terms.append(part)

        # Priority 1: Exact matches for window_class
        for app in desktop_apps:
            app_class = getattr(app, "window_class", None)
            if app_class and app_class.lower() in search_terms:
                return app

        # Priority 2: Exact matches for app name or display name
        for app in desktop_apps:
            app_names = [
                getattr(app, "name", None),
                getattr(app, "display_name", None),
            ]
            app_names = [n.lower() for n in app_names if n]
            if any(name in expanded_terms for name in app_names):
                return app

        # Priority 3: Exact matches for executable basename
        for app in desktop_apps:
            if app.executable:
                exe_base = os.path.basename(app.executable).lower()
                if exe_base in expanded_terms:
                    # If this is a common terminal or shell, only match if the name also matches
                    # This prevents Neovim (which uses 'kitty' as its executable wrapper) from overriding Kitty
                    common_wrappers = [
                        "kitty",
                        "bash",
                        "sh",
                        "zsh",
                        "python",
                        "python3",
                    ]
                    if exe_base in common_wrappers:
                        app_names = [
                            getattr(app, "name", ""),
                            getattr(app, "display_name", ""),
                        ]
                        if not any(exe_base in n.lower() for n in app_names if n):
                            continue
                    return app

        # Priority 4: Fuzzy name matching (containment)
        for app in desktop_apps:
            app_terms = [
                getattr(app, "name", ""),
                getattr(app, "display_name", ""),
                getattr(app, "window_class", ""),
            ]
            app_terms = [t.lower() for t in app_terms if t]

            for term in expanded_terms:
                if len(term) < 3:
                    continue
                if any(term in app_term for app_term in app_terms):
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
        app_identifier = self._get_app_identifier(app_data)
        if event.button == 1:  # Left click - launch app
            self._launch_app(app_data)
        elif event.button == 2:  # Middle click - unpin app
            self._unpin_app(app_identifier)
        elif event.button == 3:  # Right click - show context menu
            self.show_menu(app_identifier)
            self.menu.popup_at_pointer(event)

    def _handle_trash_click(self, event):
        """Handle trash button click to open trash in file manager"""
        if event.button == 1:  # Left click
            try:
                trash_path = os.path.expanduser("~/.local/share/Trash/files")
                file_managers = [
                    "nautilus",
                    "dolphin",
                    "thunar",
                    "nemo",
                    "caja",
                    "pcmanfm",
                ]

                for fm in file_managers:
                    try:
                        result = subprocess.run(
                            ["which", fm], capture_output=True, text=True
                        )
                        if result.returncode == 0:
                            subprocess.Popen([fm, trash_path])
                            return
                    except Exception:
                        continue
            except Exception as e:
                logger.error(f"[AppBar] Error opening trash: {e}")

    def _set_item_hover_state(self, item, is_hovered, pinned=False):
        if is_hovered:
            self._parent.on_hover_enter()

        items_list = self.pinned_items_pos if pinned else self.running_items_pos
        try:
            index = items_list.index(item)
            style_class = "semi_hovered"
            action = "add" if is_hovered else "remove"

            if index > 0:
                getattr(items_list[index - 1], f"{action}_style_class")(style_class)
            if index < len(items_list) - 1:
                getattr(items_list[index + 1], f"{action}_style_class")(style_class)
        except (ValueError, IndexError):
            pass

    def _launch_app(self, app_info):
        """Launch an app using its desktop app instance or a data dictionary"""
        try:
            command_line = ""
            if hasattr(app_info, "command_line"):
                command_line = app_info.command_line
            elif isinstance(app_info, dict):
                command_line = app_info.get("command_line") or app_info.get(
                    "executable"
                )
            elif isinstance(app_info, str):
                command_line = app_info

            if not command_line:
                # Fallback to desktop app search if it's just a string class
                desktop_apps = get_desktop_applications(include_hidden=False)
                app = self._find_desktop_app(app_info, desktop_apps)
                if app:
                    command_line = app.command_line

            if command_line:
                cleaned_command = re.sub(r"%\w+", "", command_line).strip()
                final_command = f"hyprctl dispatch exec 'uwsm app -- {cleaned_command}'"
                subprocess.Popen(final_command, shell=True)
            elif hasattr(app_info, "launch"):
                app_info.launch()
            else:
                logger.error(
                    f"[AppBar] Could not determine launch command for: {app_info}"
                )
        except Exception as e:
            logger.error(f"[AppBar] Failed to launch app: {e}")

    def _get_app_identifier(self, app_data):
        if isinstance(app_data, dict):
            return app_data.get("name", "") or app_data.get("window_class", "")
        return app_data

    def _pin_app(self, app_class: str):
        if self._is_app_pinned(app_class):
            return False

        try:
            desktop_apps = get_desktop_applications(include_hidden=False)
            app = self._find_desktop_app(app_class, desktop_apps)

            app_data = {
                "name": app.name if app else app_class,
                "display_name": (app.display_name or app.name) if app else app_class,
                "window_class": (getattr(app, "window_class", None) or app_class)
                if app
                else app_class,
                "executable": app.executable if app else app_class,
                "command_line": app.command_line if app else app_class,
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
        try:
            clients = self.get_clients()
            focused_window = self.get_focused_window()
            focused_address = (
                focused_window.get("address", "") if focused_window else ""
            )

            current_instance_ids = set()

            for client in clients:
                if client.get("hidden", False) or not self._should_show_app_instance(
                    client
                ):
                    continue

                instance_address = client.get("address", "")
                app_class = client.get("class", "") or client.get("title", "")
                if not instance_address or not app_class:
                    continue

                current_instance_ids.add(instance_address)

                if instance_address not in self.client_buttons:
                    self.create_instance_button(instance_address, client, app_class)
                else:
                    self.update_instance_button(instance_address, client, app_class)

                button = self.client_buttons[instance_address]
                if instance_address == focused_address:
                    button.add_style_class("activated")
                else:
                    button.remove_style_class("activated")

            self._update_pinned_apps_state(clients)
            self._update_separator_visibility()

            self._cleanup_removed_instances(current_instance_ids)

        except Exception as e:
            logger.error(f"[AppBar] Error in update_dock_apps: {e}")

    def _update_pinned_apps_state(self, clients):
        running_app_classes = {
            client.get("class", "").lower() or client.get("title", "").lower()
            for client in clients
            if not client.get("hidden", False)
            and (client.get("class") or client.get("title"))
            and self._should_show_app_instance(client)
        }

        for app_identifier, button in self.pinned_buttons.items():
            # Skip trash button as it's not a regular app
            if app_identifier == "trash" or hasattr(button, "is_trash"):
                continue

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

        # Clean up removed and orphaned buttons
        for instance_id in buttons_to_remove + [
            k
            for k, v in self.client_buttons.items()
            if not hasattr(v, "instance_address") or not v.get_parent()
        ]:
            if instance_id in self.client_buttons:
                button = self.client_buttons.pop(instance_id)
                try:
                    if button in self.running_items_pos:
                        self.running_items_pos.remove(button)
                    button.remove_style_class("shown")
                    button.remove_style_class("activated")
                    if button.get_parent():
                        button.get_parent().remove(button)
                    button.destroy()
                except Exception as e:
                    logger.warning(f"[AppBar] Error during cleanup: {e}")

    def create_instance_button(self, instance_address, client, app_class):
        try:
            client_image = Image(name="dock_item_icon")

            try:
                desktop_apps = get_desktop_applications(include_hidden=False)
                app = self._find_desktop_app(app_class, desktop_apps)
                pixbuf = self._get_app_icon(app_class, app)
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

            indicator = Box(name="dock_item_indicator", h_align="center")
            main_container = Box(
                name="dock_item_main_container",
                orientation="v",
                children=[image_overlay, indicator],
            )

            tooltip_text = client.get("title", app_class)
            if tooltip_text != app_class:
                tooltip_text = f"{app_class}: {tooltip_text}"

            client_button = Button(
                name="dock_item",
                child=main_container,
                tooltip_text=tooltip_text,
                on_button_press_event=lambda widget, event: self.handle_instance_click(
                    widget, event
                ),
                on_enter_notify_event=lambda *_: self._set_item_hover_state(
                    client_button, True, pinned=False
                ),
                on_leave_notify_event=lambda *_: self._set_item_hover_state(
                    client_button, False, pinned=False
                ),
            )

            client_button.instance_address = instance_address
            client_button.client_data = client
            client_button.app_class = app_class
            client_button.workspace_label = workspace_label
            client_button.add_style_class("shown")

            self.client_buttons[instance_address] = client_button
            self.running_apps_container.add(client_button)
            self.running_items_pos.append(client_button)

        except Exception as e:
            logger.error(
                f"[AppBar] Error creating instance button for {app_class}: {e}"
            )

    def _get_workspace_id(self, client):
        workspace_data = client.get("workspace", {})
        if isinstance(workspace_data, dict):
            return workspace_data.get("id")
        elif isinstance(workspace_data, (int, str)):
            return workspace_data
        return None

    def _should_show_app_instance(self, client):
        if not data.DOCK_HIDE_SPECIAL_WORKSPACE_APPS:
            return True

        workspace_id = self._get_workspace_id(client)
        return (
            False if workspace_id is None else not is_special_workspace_id(workspace_id)
        )

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

        container = button.get_child()
        if not hasattr(container, "get_children"):
            return

        children = container.get_children()
        if not children or not isinstance(children[0], Overlay):
            return

        image_overlay = children[0]
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
        has_pinned_apps = len(self.pinned_items_pos) > 0
        has_running_apps = len(self.running_items_pos) > 0
        if has_pinned_apps and has_running_apps:
            self.separator.remove_style_class("hidden")
        else:
            self.separator.add_style_class("hidden")


class Dock(Window):
    def __init__(self):
        dock_config = self._get_dock_config()
        if not data.DOCK_ENABLED:
            super().__init__(layer="top", title="dock", anchor=dock_config["anchor"])
            self.children = Box()  # Empty dock if disabled
            return

        super().__init__(layer="top", anchor=dock_config["anchor"])

        self.app_bar = AppBar(self)
        self.revealer = Revealer(
            child=Box(children=[self.app_bar], style="padding: 20px 50px 5px 50px;"),
            transition_duration=200,
            transition_type=dock_config["transition"],
        )

        self.children = EventBox(
            events=["enter-notify", "leave-notify"],
            child=Box(style="min-height: 1px", children=self.revealer),
            on_enter_notify_event=lambda *_: self.on_hover_enter(),
            on_leave_notify_event=lambda *_: self.on_hover_leave(),
        )

        self.revealer.set_reveal_child(True)
        self.app_bar.add_style_class("shown")

        self.dock_height = 100
        self.is_hovered = False
        self.hide_ticket = 0

        # Only setup occlusion monitoring if auto-hide is enabled
        if data.DOCK_AUTO_HIDE:
            self.setup_occlusion_monitoring()

    def on_hover_enter(self):
        self.is_hovered = True
        self.hide_ticket = random.getrandbits(32)
        self.revealer.set_reveal_child(True)
        self.app_bar.add_style_class("shown")

    def on_hover_leave(self):
        self.is_hovered = False
        self.hide_ticket = random.getrandbits(32)

        def delayed_hide(ticket):
            if ticket == self.hide_ticket and not self.is_hovered:
                # Only hide if we aren't occluded (or if occlusion logic says so)
                # For now, just trigger the basic hide if auto-hide is on
                if data.DOCK_AUTO_HIDE:
                    # Check if actually occluded before hiding if DOCK_ALWAYS_OCCLUDED is false
                    occlusion_pos = self._get_dock_config()["occlusion"]
                    is_occluded = data.DOCK_ALWAYS_OCCLUDED or check_occlusion(
                        (occlusion_pos, self.dock_height)
                    )
                    if is_occluded:
                        self.revealer.set_reveal_child(False)
                        self.app_bar.remove_style_class("shown")
            return False

        GLib.timeout_add(500, delayed_hide, self.hide_ticket)

    def _get_dock_config(self):
        config_map = {
            "Left": {
                "anchor": "left center",
                "transition": "slide-right",
                "occlusion": "left",
            },
            "Right": {
                "anchor": "right center",
                "transition": "slide-left",
                "occlusion": "right",
            },
            "Bottom": {
                "anchor": "bottom center",
                "transition": "slide-up",
                "occlusion": "bottom",
            },
        }
        return config_map.get(data.DOCK_POSITION, config_map["Bottom"])

    def setup_occlusion_monitoring(self):
        def check_dock_occlusion():
            try:
                if data.DOCK_ALWAYS_OCCLUDED:
                    is_occluded = True
                else:
                    occlusion_pos = self._get_dock_config()["occlusion"]
                    is_occluded = check_occlusion((occlusion_pos, self.dock_height))

                if (
                    is_occluded
                    and not self.is_hovered
                    and self.revealer.get_reveal_child()
                ):
                    self.revealer.set_reveal_child(False)
                    self.app_bar.remove_style_class("shown")
                elif not is_occluded and not self.revealer.get_reveal_child():
                    self.revealer.set_reveal_child(True)
                    self.app_bar.add_style_class("shown")
                elif is_occluded and self.is_hovered:
                    if not self.revealer.get_reveal_child():
                        self.revealer.set_reveal_child(True)
                    self.app_bar.add_style_class("shown")
            except Exception as e:
                logger.error(f"[Dock] Occlusion check error: {e}")

            return True

        GLib.timeout_add(300, check_dock_occlusion)
