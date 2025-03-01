import json
import threading
from gi.repository import GLib
from utils import IconResolver, read_config
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.eventbox import EventBox
from fabric.widgets.wayland import WaylandWindow as Window
from fabric.hyprland.widgets import get_hyprland_connection
from fabric.utils import exec_shell_command, idle_add, remove_handler


class Dock(Window):
    def __init__(self, **kwargs):
        super().__init__(
            layer="top",
            anchor="bottom center",
            exclusivity="none",
            **kwargs,
        )
        self.config = read_config()
        self.conn = get_hyprland_connection()
        self.icon = IconResolver()
        self.pinned = self.config.get("pinned_apps", [])
        self.is_hidden = False
        self.hide_id = None
        self._arranger_handler = None

        # Set up UI containers
        self.view = Box(name="viewport", orientation="h")
        self.wrapper = Box(name="dock", orientation="v", children=[self.view])
        self.hover = EventBox()
        self.hover.set_size_request(-1, 1)
        self.hover.connect("enter-notify-event", self._on_hover_enter)
        self.hover.connect("leave-notify-event", self._on_hover_leave)
        self.view.connect("enter-notify-event", self._on_hover_enter)
        self.view.connect("leave-notify-event", self._on_hover_leave)
        self.main_box = Box(orientation="v", children=[self.wrapper, self.hover])
        self.add(self.main_box)

        if self.conn.ready:
            self.update_dock()
            GLib.timeout_add(
                500, self.check_hide
            )  # Delay to ensure Hyprland loads clients
        else:
            self.conn.connect("event::ready", self.update_dock)
            self.conn.connect("event::ready", self.check_hide)

        for ev in ("activewindow", "openwindow", "closewindow", "changefloatingmode"):
            self.conn.connect(f"event::{ev}", self.update_dock)
        self.conn.connect("event::workspace", self.check_hide)

    def _on_hover_enter(self, *args):
        self.toggle_dock(show=True)

    def _on_hover_leave(self, *args):
        self.delay_hide()

    def toggle_dock(self, show):
        """Show or hide the dock immediately."""
        if show:
            if self.is_hidden:
                self.is_hidden = False
                self.wrapper.add_style_class("show-dock")
                self.wrapper.remove_style_class("hide-dock")
            if self.hide_id:
                GLib.source_remove(self.hide_id)
                self.hide_id = None
        else:
            if not self.is_hidden:
                self.is_hidden = True
                self.wrapper.add_style_class("hide-dock")
                self.wrapper.remove_style_class("show-dock")

    def delay_hide(self):
        """Schedule hiding the dock after a short delay."""
        if self.hide_id:
            GLib.source_remove(self.hide_id)
        self.hide_id = GLib.timeout_add(1000, self.hide_dock)

    def hide_dock(self):
        self.toggle_dock(show=False)
        self.hide_id = None
        return False

    def check_hide(self, *args):
        """Show the dock immediately in an empty workspace; otherwise, hide if needed."""
        clients = self.get_clients()
        current_ws = self.get_workspace()
        ws_clients = [w for w in clients if w["workspace"]["id"] == current_ws]

        if not ws_clients:
            self.toggle_dock(show=True)
        elif any(not w.get("floating") and not w.get("fullscreen") for w in ws_clients):
            self.delay_hide()
        else:
            self.toggle_dock(show=True)

    def update_dock(self, *args):
        """Refresh the dock icons based on running and pinned apps."""
        arranger_handler = getattr(self, "_arranger_handler", None)

        if arranger_handler:
            remove_handler(arranger_handler)
        clients = self.get_clients()
        running = {}
        for c in clients:
            key = c["initialClass"].lower()
            running.setdefault(key, []).append(c)
        pinned_buttons = [
            self.create_button(app, running.get(app.lower(), [])) for app in self.pinned
        ]
        open_buttons = [
            self.create_button(
                c["initialClass"], running.get(c["initialClass"].lower(), [])
            )
            for group in running.values()
            for c in group
            if c["initialClass"].lower() not in self.pinned
        ]
        children = pinned_buttons
        if pinned_buttons and open_buttons:
            children += [Box(orientation="v", v_expand=True, name="dock-separator")]
        children += open_buttons
        self.view.children = children
        idle_add(self._update_size)

    def _update_size(self):
        width, _ = self.view.get_preferred_width()
        self.set_size_request(width, -1)
        return False

    def create_button(self, app, instances):
        """Create a button for an app with an icon and an optional indicator."""
        icon_img = self.icon.get_icon_pixbuf(
            app.lower(), 30
        ) or self.icon.get_icon_pixbuf("image-missing", 30)
        items = [Image(pixbuf=icon_img)]
        if instances:
            items.append(
                Image(
                    pixbuf=self.icon.get_icon_pixbuf("filename-dot-amarok", 11),
                    name="dock-app-indicator",
                )
            )
        return Button(
            child=Box(
                name="dock-icon",
                orientation="v",
                h_align="center",
                children=items,
            ),
            on_clicked=lambda *a: self.handle_app(app, instances),
            tooltip_text=instances[0]["title"] if instances else app,
            name="dock-app-button",
        )

    def handle_app(self, app, instances):
        if not instances:
            threading.Thread(
                target=exec_shell_command, args=(f"nohup {app}",), daemon=True
            ).start()
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

    def get_clients(self):
        try:
            return json.loads(self.conn.send_command("j/clients").reply.decode())
        except json.JSONDecodeError:
            return []

    def get_focused(self):
        try:
            return json.loads(
                self.conn.send_command("j/activewindow").reply.decode()
            ).get("address", "")
        except json.JSONDecodeError:
            return ""

    def get_workspace(self):
        try:
            return json.loads(
                self.conn.send_command("j/activeworkspace").reply.decode()
            ).get("id", 0)
        except json.JSONDecodeError:
            return 0
