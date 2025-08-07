import json
import os
import re
import subprocess

from fabric.utils import get_relative_path, bulk_connect
import gi
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.eventbox import EventBox
from fabric.widgets.image import Image
from fabric.widgets.revealer import Revealer
from fabric.widgets.separator import Separator
from gi.repository import Glace, GLib, Gtk

from fabric.hyprland.widgets import get_hyprland_connection
from fabric.utils.helpers import get_desktop_applications, exec_shell_command
from utils.icon_resolver import IconResolver
from utils.occlusion import check_occlusion
from utils.roam import modus_service
from widgets.wayland import WaylandWindow as Window
from widgets.popup_window import PopupWindow
import config.data as data
from utils.functions import read_json_file, write_json_file

gi.require_version("Glace", "0.1")


# Pinned apps file
PINNED_APPS_FILE = get_relative_path("../config/assets/dock.json")


class AppBar(Box):
    def __init__(self, parent: Window):
        self.client_buttons = {}
        self._parent = parent

        self.icon_size = data.DOCK_ICON_SIZE
        self.preview_size = [200, 150]  # Default preview size
        orientation = (
            "vertical" if data.DOCK_POSITION in ["Left", "Right"] else "horizontal"
        )

        super().__init__(
            spacing=10,
            name="dock",
            children=[],
            orientation=orientation,
        )
        self.icon_resolver = IconResolver()

        self._manager = Glace.Manager()
        self._preview_image = Image()

        # Connect to Glace manager signals to automatically handle running apps
        self._manager.connect("client-added", self._on_glace_client_added)
        self._manager.connect("client-removed", self._on_glace_client_removed)

        self.glace_client_buttons = {}

        self.pinned_items_pos = []
        self.running_items_pos = []

        self.conn = get_hyprland_connection()

        self.menu = Gtk.Menu()
        self.pinned_apps_container = Box()
        self.add(self.pinned_apps_container)

        self.pinned_apps = read_json_file(PINNED_APPS_FILE)
        if self.pinned_apps is None:
            self.pinned_apps = []
        self._populate_pinned_apps(self.pinned_apps)

        self.add(Separator(name="dock-separator"))

        # Container for running apps
        self.running_apps_container = Box(name="running-apps-container")
        self.add(self.running_apps_container)

        # Setup preview popup if enabled
        if data.DOCK_PREVIEW_APPS:
            self._setup_preview_popup()

        if not self.pinned_apps:
            placeholder = Button(
                name="dock-app-button",
                image=Image(
                    icon_name="view-app-grid-symbolic", icon_size=self.icon_size
                ),
                tooltip_text="Application Menu",
            )
            self.pinned_apps_container.add(placeholder)

        # Connect to modus service signals for dock apps changes
        if modus_service:
            modus_service.connect("dock-apps-changed", self._on_dock_apps_changed)
            modus_service.connect(
                "current-workspace-changed", self._on_workspace_changed
            )
            modus_service.connect(
                "current-active-app-name-changed", self._on_active_app_changed
            )
            self._update_modus_service_dock_apps()
        GLib.timeout_add(1000, self._delayed_update)

    def _setup_preview_popup(self):
        self.popup_revealer = Revealer(
            child=Box(
                children=self._preview_image,
                style_classes=["window-basic", "sleek-border"],
            ),
            transition_type="crossfade",
            transition_duration=400,
        )

        self.popup = PopupWindow(
            parent=self._parent,
            margin="0px 0px 80px 0px",
            visible=False,
            enable_boundary_checking=False,  # Disable boundary checking for dock previews
        )
        self.popup.children = self.popup_revealer

        self.popup_revealer.connect(
            "notify::child-revealed",
            lambda *_: (
                self.popup.set_visible(False)
                if not self.popup_revealer.child_revealed
                else None
            ),
        )

    def update_preview_image_glace(self, client, client_button: Button):
        if not hasattr(self, "popup") or not self.popup:
            return

        self.popup.set_pointing_to(client_button)

        def capture_callback(pbuf, _):
            self._preview_image.set_from_pixbuf(
                pbuf.scale_simple(self.preview_size[0], self.preview_size[1], 2)
            )
            self.popup.set_visible(True)
            self.popup_revealer.reveal()

        try:
            self._manager.capture_client(
                client=client,
                overlay_cursor=False,
                callback=capture_callback,
                user_data=None,
            )
        except Exception as e:
            pass

    def hide_preview(self):
        if hasattr(self, "popup_revealer") and self.popup_revealer:
            self.popup_revealer.unreveal()

    def handle_item_hovered(self, item, is_pinned=False):
        try:
            if is_pinned:
                if item in self.pinned_items_pos:
                    index = self.pinned_items_pos.index(item)
                    # Add semi_hovered to previous item
                    if index > 0:
                        self.pinned_items_pos[index - 1].add_style_class("semi_hovered")
                    # Add semi_hovered to next item
                    if index < len(self.pinned_items_pos) - 1:
                        self.pinned_items_pos[index + 1].add_style_class("semi_hovered")
            else:
                if item in self.running_items_pos:
                    index = self.running_items_pos.index(item)
                    # Add semi_hovered to previous item
                    if index > 0:
                        self.running_items_pos[index - 1].add_style_class(
                            "semi_hovered"
                        )
                    # Add semi_hovered to next item
                    if index < len(self.running_items_pos) - 1:
                        self.running_items_pos[index + 1].add_style_class(
                            "semi_hovered"
                        )
        except (ValueError, IndexError):
            pass

    def handle_item_unhovered(self, item, is_pinned=False):
        try:
            if is_pinned:
                if item in self.pinned_items_pos:
                    index = self.pinned_items_pos.index(item)
                    # Remove semi_hovered from previous item
                    if index > 0:
                        self.pinned_items_pos[index - 1].remove_style_class(
                            "semi_hovered"
                        )
                    # Remove semi_hovered from next item
                    if index < len(self.pinned_items_pos) - 1:
                        self.pinned_items_pos[index + 1].remove_style_class(
                            "semi_hovered"
                        )
            else:
                if item in self.running_items_pos:
                    index = self.running_items_pos.index(item)
                    # Remove semi_hovered from previous item
                    if index > 0:
                        self.running_items_pos[index - 1].remove_style_class(
                            "semi_hovered"
                        )
                    # Remove semi_hovered from next item
                    if index < len(self.running_items_pos) - 1:
                        self.running_items_pos[index + 1].remove_style_class(
                            "semi_hovered"
                        )
        except (ValueError, IndexError):
            pass

    def clear_all_hover_effects(self):
        try:
            # Clear semi_hovered from all pinned items
            for item in self.pinned_items_pos:
                item.remove_style_class("semi_hovered")

            # Clear semi_hovered from all running items
            for item in self.running_items_pos:
                item.remove_style_class("semi_hovered")

            # Hide preview popup if it's showing
            if hasattr(self, "popup_revealer") and self.popup_revealer:
                self.popup_revealer.unreveal()
        except Exception:
            pass

    def _delayed_update(self):
        self.update_dock()
        return False  # Don't repeat the timeout

    def _on_glace_client_added(self, _, client):
        try:
            client_image = Image()

            def on_button_press_event(event, client):
                if event.button == 1:
                    try:
                        # Try to use Glace client methods if available
                        if (
                            hasattr(client, "get_activated")
                            and hasattr(client, "get_minimized")
                            and hasattr(client, "get_maximized")
                        ):
                            if not client.get_activated():
                                client.activate()
                            elif client.get_minimized():
                                client.unminimize()
                            elif client.get_maximized():
                                client.unmaximize()
                            else:
                                client.maximize()
                        else:
                            # Fallback to simple activate
                            client.activate()
                    except Exception:
                        # Final fallback to simple activate
                        try:
                            client.activate()
                        except Exception:
                            pass
                elif event.button == 2:
                    # Middle click: Pin the app to dock
                    app_id = client.get_app_id()
                    if app_id and not self.check_if_pinned(app_id):
                        self._pin_app(app_id)
                elif event.button == 3:
                    # Show context menu for running app
                    app_id = client.get_app_id()
                    self.show_menu(app_id, client)
                    self.menu.popup_at_pointer(event)

            def on_app_id(*_):
                app_id = client.get_app_id()
                if not app_id:
                    return

                client_image.set_from_pixbuf(
                    self.icon_resolver.get_icon_pixbuf(app_id, self.icon_size)
                )

                title = client.get_title()
                client_button.set_tooltip_text(title if title else app_id)

            def create_glace_hover_handlers(button):
                def on_enter(*_):
                    self.handle_item_hovered(button, False)
                    if data.DOCK_PREVIEW_APPS:
                        self.update_preview_image_glace(client, button)

                def on_leave(*_):
                    self.handle_item_unhovered(button, False)
                    if data.DOCK_PREVIEW_APPS:
                        self.popup_revealer.unreveal()

                return on_enter, on_leave

            client_button = Button(
                name="dock-app-button",
                image=client_image,
                events=["enter-notify", "leave-notify"],
                on_button_press_event=lambda _, event: on_button_press_event(
                    event, client
                ),
            )

            # Connect hover handlers after button creation
            hover_enter, hover_leave = create_glace_hover_handlers(client_button)
            client_button.connect("enter-notify-event", hover_enter)
            client_button.connect("leave-notify-event", hover_leave)

            self.glace_client_buttons[client.get_id()] = client_button
            # Add to running items position tracking
            self.running_items_pos.append(client_button)

            bulk_connect(
                client,
                {
                    "notify::app-id": on_app_id,
                    "close": lambda *_: self._remove_glace_client_button(client),
                },
            )

            self.running_apps_container.add(client_button)

        except Exception:
            pass

    def _on_glace_client_removed(self, _, client):
        self._remove_glace_client_button(client)

    def _remove_glace_client_button(self, client):
        try:
            client_id = client.get_id()
            if client_id in self.glace_client_buttons:
                button = self.glace_client_buttons[client_id]
                # Remove from position tracking
                if button in self.running_items_pos:
                    self.running_items_pos.remove(button)
                self.running_apps_container.remove(button)
                del self.glace_client_buttons[client_id]
        except Exception:
            pass

    def _populate_pinned_apps(self, apps):
        self.pinned_apps_container.children = []
        # Clear pinned items position tracking
        self.pinned_items_pos = []

        try:
            desktop_apps = get_desktop_applications(include_hidden=False)
        except Exception:
            desktop_apps = []

        for app_id in apps:
            app = self._find_desktop_app(app_id, desktop_apps)
            if app:

                def on_button_press_event(_, event, app=app, app_id=app_id):
                    if event.button == 1:  # Left click
                        self._launch_app(app)
                    elif event.button == 2:  # Middle click
                        # Unpin the app from dock
                        self._unpin_app(app_id)
                    elif event.button == 3:  # Right click
                        self.show_menu(app_id)
                        self.menu.popup_at_pointer(event)

                def create_hover_handlers(button):
                    return (
                        lambda *_: self.handle_item_hovered(button, True),
                        lambda *_: self.handle_item_unhovered(button, True),
                    )

                pinned_button = Button(
                    name="dock-app-button",
                    image=Image(pixbuf=app.get_icon_pixbuf(self.icon_size)),
                    tooltip_text=app.display_name or app.name,
                    events=["enter-notify", "leave-notify"],
                    on_button_press_event=on_button_press_event,
                )

                # Connect hover handlers after button creation
                hover_enter, hover_leave = create_hover_handlers(pinned_button)
                pinned_button.connect("enter-notify-event", hover_enter)
                pinned_button.connect("leave-notify-event", hover_leave)

                # Add to pinned items position tracking
                self.pinned_items_pos.append(pinned_button)
                self.pinned_apps_container.add(pinned_button)

    def _find_desktop_app(self, app_id: str, desktop_apps):
        for app in desktop_apps:

            if (
                (app.name and app.name.lower() == app_id.lower())
                or (app.display_name and app.display_name.lower() == app_id.lower())
                or (
                    hasattr(app, "window_class")
                    and app.window_class
                    and app.window_class.lower() == app_id.lower()
                )
                or (app.executable and app.executable.lower() == app_id.lower())
                or (
                    app.executable
                    and os.path.basename(app.executable).lower() == app_id.lower()
                )
            ):
                return app
        return None

    def _launch_app(self, app):
        try:
            cleaned_command = re.sub(r"%\w+", "", app.command_line).strip()
            final_command = f"hyprctl dispatch exec 'uwsm app -- {cleaned_command}'"
            subprocess.Popen(final_command, shell=True)

        except Exception as e:
            try:
                app.launch()
            except Exception as fallback_error:
                pass

    def check_if_pinned(self, app_id: str) -> bool:
        return app_id in self.pinned_apps

    def show_menu(self, app_id: str, client=None, window_address=None):
        for item in self.menu.get_children():
            self.menu.remove(item)
            item.destroy()

        if client or window_address:
            close_item = Gtk.MenuItem(label="Close")
            if client:
                close_item.connect(
                    "activate", lambda *_: self._close_running_app(client)
                )
            self.menu.add(close_item)

            # Add separator if we have both close and pin options
            if app_id:
                separator = Gtk.SeparatorMenuItem()
                self.menu.add(separator)

        # Add Pin/Unpin option (for both pinned and running apps)
        if app_id:
            pin_item = Gtk.MenuItem(label="Pin")
            if self.check_if_pinned(app_id):
                pin_item.set_label("Unpin")
                pin_item.connect("activate", lambda *_: self._unpin_app(app_id))
            else:
                pin_item.connect("activate", lambda *_: self._pin_app(app_id))
            self.menu.add(pin_item)

        self.menu.show_all()

    def _close_running_app(self, client):
        try:
            # Try to close the client gracefully first
            client.close()
        except Exception:
            # If that fails, try to get the app_id and use hyprctl to kill the window
            try:
                app_id = client.get_app_id()
                if app_id:
                    # Use hyprctl to kill windows of this application class
                    exec_shell_command(f"hyprctl dispatch closewindow class:{app_id}")
            except Exception:
                # Last resort: kill active window (not ideal but better than nothing)
                try:
                    exec_shell_command("hyprctl dispatch killactive")
                except Exception:
                    pass

    def _unpin_app(self, app_id: str):
        if not self.check_if_pinned(app_id):
            return False

        self.pinned_apps.remove(app_id)
        write_json_file(self.pinned_apps, PINNED_APPS_FILE)
        self._populate_pinned_apps(self.pinned_apps)
        self._update_modus_service_dock_apps()
        return True

    def _pin_app(self, app_id: str):
        if self.check_if_pinned(app_id):
            return False

        self.pinned_apps.append(app_id)
        write_json_file(self.pinned_apps, PINNED_APPS_FILE)
        self._populate_pinned_apps(self.pinned_apps)
        self._update_modus_service_dock_apps()
        return True

    def update_dock(self, *args):
        try:
            if hasattr(self, "running_apps_container"):
                self.running_apps_container.show_all()

        except Exception as e:
            pass

    def _update_modus_service_dock_apps(self):
        if modus_service:
            try:
                dock_apps_json = json.dumps(self.pinned_apps)
                modus_service.dock_apps = dock_apps_json
            except Exception as e:
                pass

    def _on_dock_apps_changed(self, service, new_dock_apps: str):
        new_pinned_apps = json.loads(new_dock_apps) if new_dock_apps else []
        if new_pinned_apps != self.pinned_apps:
            self.pinned_apps = new_pinned_apps
            write_json_file(self.pinned_apps, PINNED_APPS_FILE)
            self._populate_pinned_apps(self.pinned_apps)

    def _on_workspace_changed(self, service, new_workspace: str):
        self.update_dock()

    def _on_active_app_changed(self, service, new_active_app: str):
        self.update_dock()


class Dock(Window):
    def __init__(self):
        self.dock_enabled = data.DOCK_ENABLED
        anchor_map = {
            "Bottom": "bottom center",
            "Left": "left center",
            "Right": "right center",
        }
        anchor = anchor_map.get(data.DOCK_POSITION, "bottom center")

        super().__init__(
            layer="top",
            title="modus",
            anchor=anchor,
        )
        if data.DOCK_POSITION == "Left":
            transition_type = "slide-right"
            padding_style = "padding: 50px 5px 50px 20px;"
        elif data.DOCK_POSITION == "Right":
            transition_type = "slide-left"
            padding_style = "padding: 50px 20px 50px 5px;"
        else:  # Bottom
            transition_type = "slide-up"
            padding_style = "padding: 20px 50px 5px 50px;"

        self.app_bar = AppBar(self)
        self.revealer = Revealer(
            child=Box(children=[self.app_bar], style=padding_style),
            transition_duration=500,
            transition_type=transition_type,
        )

        if data.DOCK_AUTO_HIDE:
            self.children = EventBox(
                events=["enter-notify", "leave-notify"],
                child=Box(style="min-height: 1px", children=self.revealer),
                on_enter_notify_event=lambda *_: self.on_hover_enter(),
                on_leave_notify_event=lambda *_: self.on_hover_leave(),
            )
        else:
            self.children = EventBox(
                events=["enter-notify", "leave-notify"],
                child=Box(children=self.revealer, style="min-height: 60px;"),
                on_leave_notify_event=lambda *_: self.on_hover_leave_no_autohide(),
            )

        if data.DOCK_AUTO_HIDE:
            self.revealer.set_reveal_child(False)
        else:
            self.revealer.set_reveal_child(True)

        if not data.DOCK_ENABLED:
            self.set_visible(False)
        else:
            self.set_visible(True)

        # Set up occlusion checking
        self.dock_height = 100
        self.is_hovered = False
        self.hide_timeout_id = None

        # Only setup occlusion monitoring if auto-hide is enabled
        if data.DOCK_AUTO_HIDE:
            self.setup_occlusion_monitoring()

        # Connect to modus service for dock visibility control
        if modus_service:
            modus_service.connect("dock-hidden-changed", self._on_dock_hidden_changed)
            modus_service.connect("dock-width-changed", self._on_dock_width_changed)
            modus_service.connect("dock-height-changed", self._on_dock_height_changed)

    def on_hover_enter(self):
        self.is_hovered = True
        if self.hide_timeout_id:
            GLib.source_remove(self.hide_timeout_id)
            self.hide_timeout_id = None
        self.revealer.set_reveal_child(True)

    def on_hover_leave(self):
        self.is_hovered = False
        if hasattr(self, "app_bar"):
            self.app_bar.clear_all_hover_effects()

    def on_hover_leave_no_autohide(self):
        if hasattr(self, "app_bar"):
            self.app_bar.clear_all_hover_effects()

    def setup_occlusion_monitoring(self):
        def check_dock_occlusion():
            try:
                if data.DOCK_POSITION == "Left":
                    position = ("left", self.dock_height)
                elif data.DOCK_POSITION == "Right":
                    position = ("right", self.dock_height)
                else:  # Bottom
                    position = ("bottom", self.dock_height)

                if data.DOCK_ALWAYS_OCCLUDED:
                    is_occluded = True
                else:
                    is_occluded = check_occlusion(position)

                current_visible = self.revealer.get_reveal_child()

                if is_occluded and not self.is_hovered and current_visible:
                    self.revealer.set_reveal_child(False)
                elif not is_occluded and not current_visible and not self.is_hovered:
                    self.revealer.set_reveal_child(True)

            except Exception as e:
                pass

            return True

        GLib.timeout_add(250, check_dock_occlusion)

    def _update_size(self):
        try:
            if hasattr(self, "revealer") and self.revealer.get_child():
                app_bar = self.revealer.get_child().get_children()[0]
                if hasattr(app_bar, "get_preferred_width"):
                    width, _ = app_bar.get_preferred_width()
                    height, _ = app_bar.get_preferred_height()
                    self.set_size_request(width, height)
        except Exception as e:
            pass
        return False

    def _on_dock_hidden_changed(self, service, hidden: bool):
        try:
            if hidden:
                self.revealer.set_reveal_child(False)
                self.set_visible(False)
            else:
                self.set_visible(True)
                self.revealer.set_reveal_child(True)
        except Exception as e:
            pass

    def _on_dock_width_changed(self, service, width: int):
        try:
            # Could be used to adjust dock width dynamically
            # For now, just log the change
            pass
        except Exception as e:
            pass

    def _on_dock_height_changed(self, service, height: int):
        try:
            self.dock_height = height if height > 0 else 100
        except Exception as e:
            pass

    def reload_data(self):
        if not data.DOCK_ENABLED and self.dock_enabled:
            self.set_visible(False)
            self.dock_enabled = False
        elif data.DOCK_ENABLED and not self.dock_enabled:
            self.set_visible(True)
            self.dock_enabled = True
        # Update auto-hide behavior
        if hasattr(self, "revealer"):
            if data.DOCK_AUTO_HIDE:
                if not hasattr(self, "is_hovered"):
                    self.setup_occlusion_monitoring()
            else:
                self.revealer.set_reveal_child(True)
