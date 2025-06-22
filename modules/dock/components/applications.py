import json
import logging

import cairo
import config.data as data
from fabric.hyprland.widgets import get_hyprland_connection
from fabric.utils import exec_shell_command, exec_shell_command_async, get_relative_path
from fabric.utils.helpers import get_desktop_applications
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from gi.repository import Gdk, GLib, Gtk
from utils.icon_resolver import IconResolver


def read_config():
    config_path = get_relative_path("../../../config/json/dock.json")
    try:
        with open(config_path, "r") as file:
            config_data = json.load(file)

        if (
            "pinned_apps" in config_data
            and config_data["pinned_apps"]
            and isinstance(config_data["pinned_apps"][0], str)
        ):
            all_apps = get_desktop_applications()
            app_map = {app.name: app for app in all_apps if app.name}

            old_pinned = config_data["pinned_apps"]
            config_data["pinned_apps"] = []

            for app_id in old_pinned:
                app = app_map.get(app_id)
                if app:
                    app_data_obj = {
                        "name": app.name,
                        "display_name": app.display_name,
                        "window_class": app.window_class,
                        "executable": app.executable,
                        "command_line": app.command_line,
                    }
                    config_data["pinned_apps"].append(app_data_obj)
                else:
                    config_data["pinned_apps"].append({"name": app_id})

    except (FileNotFoundError, json.JSONDecodeError):
        config_data = {"pinned_apps": []}
    return config_data


def createSurfaceFromWidget(widget: Gtk.Widget) -> cairo.ImageSurface:
    alloc = widget.get_allocation()
    surface = cairo.ImageSurface(
        cairo.Format.ARGB32,
        alloc.width,
        alloc.height,
    )
    cr = cairo.Context(surface)
    cr.set_source_rgba(255, 255, 255, 0)
    cr.rectangle(0, 0, alloc.width, alloc.height)
    cr.fill()
    widget.draw(cr)
    return surface


class Applications(Box):
    def __init__(self, orientation_val="h", dock_instance=None, **kwargs):
        super().__init__(
            name="applications-dock", orientation=orientation_val, spacing=4, **kwargs
        )

        self.hide()

        self.dock_instance = dock_instance

        self.config = read_config()
        self.conn = get_hyprland_connection()
        self.icon_resolver = IconResolver()
        self.pinned = self.config.get("pinned_apps", [])
        self.config_path = get_relative_path("../../../config/json/dock.json")
        self.app_map = {}
        self._all_apps = get_desktop_applications()
        self.app_identifiers = self._build_app_identifiers_map()
        self._drag_in_progress = False

        self.update_applications()

        if self.conn.ready:
            pass
        else:
            self.conn.connect("event::ready", lambda *args: self.update_applications())

        for ev in ("activewindow", "openwindow", "closewindow", "changefloatingmode"):
            self.conn.connect(f"event::{ev}", lambda *args: self.update_applications())

        GLib.timeout_add_seconds(1, self.check_config_change)

    def _build_app_identifiers_map(self):
        identifiers = {}
        for app in self._all_apps:
            if app.name:
                identifiers[app.name.lower()] = app
            if app.display_name:
                identifiers[app.display_name.lower()] = app
            if app.window_class:
                identifiers[app.window_class.lower()] = app
            if app.executable:
                identifiers[app.executable.split("/")[-1].lower()] = app
            if app.command_line:
                identifiers[app.command_line.split()[0].split("/")[-1].lower()] = app
        return identifiers

    def find_app_by_key(self, key):
        if not key:
            return None
        key_lower = key.lower() if isinstance(key, str) else ""
        return self.app_identifiers.get(key_lower)

    def find_app(self, app_identifier):
        if not app_identifier:
            return None
        if isinstance(app_identifier, dict):
            for key in [
                "window_class",
                "executable",
                "command_line",
                "name",
                "display_name",
            ]:
                if key in app_identifier and app_identifier[key]:
                    app = self.find_app_by_key(app_identifier[key])
                    if app:
                        return app
            return None
        return self.find_app_by_key(app_identifier)

    def create_button(self, app_identifier, instances):
        desktop_app = self.find_app(app_identifier)
        icon_img = None
        display_name = None
        icon_size = data.DOCK_ICON_SIZE

        if desktop_app:
            icon_img = desktop_app.get_icon_pixbuf(size=icon_size)
            display_name = desktop_app.display_name or desktop_app.name

        id_value = (
            app_identifier["name"]
            if isinstance(app_identifier, dict)
            else app_identifier
        )

        if not icon_img:
            icon_img = self.icon_resolver.get_icon_pixbuf(id_value, icon_size)

        if not icon_img:
            icon_img = self.icon_resolver.get_icon_pixbuf(
                "application-x-executable-symbolic", icon_size
            )
            if not icon_img:
                icon_img = self.icon_resolver.get_icon_pixbuf(
                    "image-missing", icon_size
                )

        items = [Image(pixbuf=icon_img)]
        tooltip = display_name or (id_value if isinstance(id_value, str) else "Unknown")
        if not display_name and instances and instances[0].get("title"):
            tooltip = instances[0]["title"]

        button = Button(
            child=Box(
                name="dock-icon", orientation="v", h_align="center", children=items
            ),
            on_clicked=lambda *a: self.handle_app(
                app_identifier, instances, desktop_app
            ),
            tooltip_text=tooltip,
            name="dock-app-button",
        )
        button.app_identifier = app_identifier
        button.desktop_app = desktop_app
        button.instances = instances
        if instances:
            button.add_style_class("instance")

        button.drag_source_set(
            Gdk.ModifierType.BUTTON1_MASK,
            [Gtk.TargetEntry.new("text/plain", Gtk.TargetFlags.SAME_APP, 0)],
            Gdk.DragAction.MOVE,
        )

        button.drag_dest_set(
            Gtk.DestDefaults.ALL,
            [Gtk.TargetEntry.new("text/plain", Gtk.TargetFlags.SAME_APP, 0)],
            Gdk.DragAction.MOVE,
        )

        button.connect("drag-begin", self.on_drag_begin)
        button.connect("drag-data-get", self.on_drag_data_get)
        button.connect("drag-data-received", self.on_drag_data_received)
        button.connect("drag-end", self.on_drag_end)
        button.connect("button-press-event", self.on_button_press)

        return button

    def handle_app(self, app_identifier, instances, desktop_app=None):
        if not instances:
            if not desktop_app:
                desktop_app = self.find_app(app_identifier)
            if desktop_app:
                launch_success = desktop_app.launch()
                if not launch_success:
                    if desktop_app.command_line:
                        exec_shell_command_async(f"nohup {desktop_app.command_line} &")
                    elif desktop_app.executable:
                        exec_shell_command_async(f"nohup {desktop_app.executable} &")
            else:
                cmd_to_run = None
                if isinstance(app_identifier, dict):
                    if (
                        "command_line" in app_identifier
                        and app_identifier["command_line"]
                    ):
                        cmd_to_run = app_identifier["command_line"]
                    elif (
                        "executable" in app_identifier and app_identifier["executable"]
                    ):
                        cmd_to_run = app_identifier["executable"]
                    elif "name" in app_identifier and app_identifier["name"]:
                        cmd_to_run = app_identifier["name"]
                elif isinstance(app_identifier, str):
                    cmd_to_run = app_identifier
                if cmd_to_run:
                    exec_shell_command_async(f"nohup {cmd_to_run} &")
        else:
            focused = self.get_focused()
            idx = next(
                (i for i, inst in enumerate(instances) if inst["address"] == focused),
                -1,
            )
            next_inst = instances[(idx + 1) % len(instances)]
            exec_shell_command(
                f"hyprctl dispatch focuswindow address:{next_inst['address']}"
            )

    def update_pinned_apps_file(self):
        config_path = get_relative_path("../../../config/json/dock.json")
        try:
            with open(config_path, "w") as file:
                json.dump(self.config, file, indent=4)
            return True
        except Exception as e:
            logging.error(f"Failed to write dock config: {e}")
            return False

    def check_config_change(self):
        new_config = read_config()
        if new_config.get("pinned_apps", []) != self.config.get("pinned_apps", []):
            self.config = new_config
            self.pinned = self.config.get("pinned_apps", [])
            self.update_app_map()
            self.update_applications()
        return True

    def update_app_map(self):
        self._all_apps = get_desktop_applications()
        self.app_identifiers = self._build_app_identifiers_map()

    def _normalize_window_class(self, class_name):
        if not class_name:
            return ""
        normalized = class_name.lower()
        suffixes = [".bin", ".exe", ".so", "-bin", "-gtk"]
        for suffix in suffixes:
            if normalized.endswith(suffix):
                normalized = normalized[: -len(suffix)]
        return normalized

    def update_applications(self):
        for child in self.get_children():
            self.remove(child)

        clients = []
        try:
            clients_data = self.conn.send_command("j/clients").reply
            if clients_data:
                clients = json.loads(clients_data.decode("utf-8"))
        except Exception as e:
            logging.error(f"Failed to get clients: {e}")

        running_windows = {}
        for client in clients:
            class_name = client.get("class", "").lower()
            if class_name:
                if class_name not in running_windows:
                    running_windows[class_name] = []
                running_windows[class_name].append(client)

        pinned_buttons = []
        used_window_classes = set()

        for app_data_item in self.pinned:
            app = self.find_app(app_data_item)
            instances = []
            matched_class = None
            possible_identifiers = []

            if isinstance(app_data_item, dict):
                for key in [
                    "window_class",
                    "executable",
                    "command_line",
                    "name",
                    "display_name",
                ]:
                    if key in app_data_item and app_data_item[key]:
                        possible_identifiers.append(app_data_item[key].lower())
            elif isinstance(app_data_item, str):
                possible_identifiers.append(app_data_item.lower())

            for class_name, window_instances in running_windows.items():
                for identifier in possible_identifiers:
                    if identifier in class_name or class_name in identifier:
                        instances = window_instances
                        matched_class = class_name
                        break
                if matched_class:
                    break

            if matched_class:
                used_window_classes.add(matched_class)

            pinned_buttons.append(self.create_button(app_data_item, instances))

        open_buttons = []
        for class_name, instances in running_windows.items():
            if class_name not in used_window_classes:
                app = self.find_app_by_key(class_name)

                if app:
                    app_data_obj = {
                        "name": app.name,
                        "display_name": app.display_name,
                        "window_class": app.window_class,
                        "executable": app.executable,
                        "command_line": app.command_line,
                    }
                    identifier = app_data_obj
                else:
                    identifier = class_name

                open_buttons.append(self.create_button(identifier, instances))

        children = pinned_buttons

        if pinned_buttons and open_buttons:
            separator_orientation = (
                Gtk.Orientation.VERTICAL
                if self.get_orientation() == Gtk.Orientation.HORIZONTAL
                else Gtk.Orientation.HORIZONTAL
            )

            children.append(
                Box(
                    orientation=separator_orientation,
                    v_expand=False,
                    h_expand=False,
                    h_align="center",
                    v_align="center",
                    name="dock-separator",
                )
            )

        children += open_buttons

        for child in children:
            self.add(child)

        if len(children) > 0:
            self.show_all()
        else:
            self.hide()

        self._update_visibility_based_on_content()

        return True

    def _update_visibility_based_on_content(self):
        has_content = len(self.get_children()) > 0

        if not has_content:
            self.hide()
        else:
            if data.DOCK_COMPONENTS_VISIBILITY.get("applications", True):
                self.show_all()
            else:
                self.hide()

    def update_pinned_apps(self, app_identifier, index=None):
        is_pinned = False
        for pinned_app in self.pinned:
            if (
                isinstance(app_identifier, dict)
                and isinstance(pinned_app, dict)
                and app_identifier.get("name") == pinned_app.get("name")
            ):
                is_pinned = True
                break
            elif app_identifier == pinned_app:
                is_pinned = True
                break

        if not is_pinned:
            if hasattr(app_identifier, "desktop_app") and app_identifier.desktop_app:
                app = app_identifier.desktop_app
                app_data_obj = {
                    "name": app.name,
                    "display_name": app.display_name,
                    "window_class": app.window_class,
                    "executable": app.executable,
                    "command_line": app.command_line,
                }
                if index is not None:
                    self.pinned.insert(index, app_data_obj)
                else:
                    self.pinned.append(app_data_obj)
            else:
                if index is not None:
                    self.pinned.insert(index, app_identifier)
                else:
                    self.pinned.append(app_identifier)

            self.config["pinned_apps"] = self.pinned
            self.update_pinned_apps_file()
            self.update_applications()

    def on_button_press(self, widget, event):
        if event.button == 3:  # Right mouse button
            app_identifier = widget.app_identifier
            self.update_pinned_apps(app_identifier)
            return True
        return False

    def on_drag_begin(self, widget, drag_context):
        self._drag_in_progress = True
        Gtk.drag_set_icon_surface(drag_context, createSurfaceFromWidget(widget))

        # Prevent dock from hiding during drag
        if self.dock_instance:
            self.dock_instance.prevent_hiding(True)

        # Store the source widget for later use
        self._dragged_widget = widget

    def on_drag_data_get(self, widget, drag_context, data_obj, info, time):
        children = self.get_children()
        index = children.index(widget)
        data_obj.set_text(str(index), -1)

    def on_drag_data_received(self, widget, drag_context, x, y, data_obj, info, time):
        try:
            source_index = int(data_obj.get_text())
        except (TypeError, ValueError):
            return

        children = self.get_children()
        target_index = children.index(widget)

        if source_index != target_index:
            separator_index = -1
            for i, child in enumerate(children):
                if child.get_name() == "dock-separator":
                    separator_index = i
                    break

            cross_section_drag_to_pin = separator_index != -1 and (
                source_index > separator_index and target_index < separator_index
            )

            cross_section_drag_to_unpin = separator_index != -1 and (
                source_index < separator_index and target_index > separator_index
            )

            if cross_section_drag_to_pin:
                source_widget = children[source_index]
                app_identifier = source_widget.app_identifier

                if hasattr(source_widget, "desktop_app") and source_widget.desktop_app:
                    app = source_widget.desktop_app
                    app_data_obj = {
                        "name": app.name,
                        "display_name": app.display_name,
                        "window_class": app.window_class,
                        "executable": app.executable,
                        "command_line": app.command_line,
                    }
                    self.pinned.insert(target_index, app_data_obj)
                else:
                    self.pinned.insert(target_index, app_identifier)

                self.config["pinned_apps"] = self.pinned
                self.update_pinned_apps_file()
                self.update_applications()
            elif cross_section_drag_to_unpin:
                if source_index < len(self.pinned):
                    self.pinned.pop(source_index)
                    self.config["pinned_apps"] = self.pinned
                    self.update_pinned_apps_file()
                    self.update_applications()
            else:
                if source_index < separator_index and target_index < separator_index:
                    item = self.pinned.pop(source_index)
                    self.pinned.insert(target_index, item)
                    self.config["pinned_apps"] = self.pinned
                    self.update_pinned_apps_file()
                    self.update_applications()
                elif source_index > separator_index and target_index > separator_index:
                    child_to_move = children.pop(source_index)
                    children.insert(target_index, child_to_move)

                    for child in self.get_children():
                        self.remove(child)
                    for child in children:
                        self.add(child)
                    self.show_all()

    def on_drag_end(self, widget, drag_context):
        if not self._drag_in_progress:
            return

        self._drag_in_progress = False
        if self.dock_instance:
            self.dock_instance.prevent_hiding(False)

        if hasattr(self, "_dragged_widget") and self._dragged_widget:
            children = self.get_children()
            source_index = children.index(self._dragged_widget)

            separator_index = -1
            for i, child in enumerate(children):
                if child.get_name() == "dock-separator":
                    separator_index = i
                    break

            if separator_index != -1 and source_index < separator_index:
                if source_index < len(self.pinned):
                    self.pinned.pop(source_index)
                    self.config["pinned_apps"] = self.pinned
                    self.update_pinned_apps_file()
                    self.update_applications()

        if hasattr(self, "_dragged_widget"):
            delattr(self, "_dragged_widget")

    def get_focused(self):
        try:
            return json.loads(
                self.conn.send_command("j/activewindow").reply.decode()
            ).get("address", "")
        except json.JSONDecodeError:
            return ""
