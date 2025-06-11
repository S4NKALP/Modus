import json
import config.data as data
from fabric.hyprland.widgets import get_hyprland_connection

from fabric.widgets.box import Box
from fabric.widgets.eventbox import EventBox
from fabric.widgets.revealer import Revealer
from gi.repository import Gdk, GLib, Gtk
from modules.corners import MyCorner
from utils.occlusion import check_occlusion
from utils.wayland import WaylandWindow as Window
from modules.dock.components.components import DockComponents


class Dock(Window):
    _instances = []

    def __init__(self, **kwargs):
        self.icon_size = 28
        self.effective_occlusion_size = 36 + self.icon_size

        anchor_to_set: str
        revealer_transition_type: str

        self.actual_dock_is_horizontal: bool
        main_box_orientation_val: Gtk.Orientation
        main_box_h_align_val: str
        dock_wrapper_orientation_val: Gtk.Orientation

        self.actual_dock_is_horizontal = not data.VERTICAL

        if self.actual_dock_is_horizontal:
            anchor_to_set = "bottom"
            revealer_transition_type = "slide-up"
            main_box_orientation_val = Gtk.Orientation.VERTICAL
            main_box_h_align_val = "center"
            dock_wrapper_orientation_val = Gtk.Orientation.HORIZONTAL
        else:
            # Use DOCK_POSITION directly instead of BAR_POSITION
            if data.DOCK_POSITION == "Left":
                anchor_to_set = "left"
                revealer_transition_type = "slide-right"
            elif data.DOCK_POSITION == "Right":
                anchor_to_set = "right"
                revealer_transition_type = "slide-left"
            else:
                anchor_to_set = "right"
                revealer_transition_type = "slide-left"

            main_box_orientation_val = Gtk.Orientation.HORIZONTAL
            main_box_h_align_val = "end" if anchor_to_set == "right" else "start"
            dock_wrapper_orientation_val = Gtk.Orientation.VERTICAL

        super().__init__(
            name="dock-window",
            layer="top",
            anchor=anchor_to_set,
            margin="0px 0px 0px 0px",  # Set all margins to 0
            exclusivity="auto" if not data.DOCK_AUTO_HIDE else "none",
            **kwargs,
        )
        Dock._instances.append(self)

        self.conn = get_hyprland_connection()

        self.hide_id = None
        self._arranger_handler = None
        self._drag_in_progress = False
        self.always_occluded = data.DOCK_ALWAYS_OCCLUDED
        self.is_mouse_over_dock_area = False
        self._prevent_occlusion = False

        self.view = Box(name="viewport", spacing=4)
        self.wrapper = Box(
            name="dock",
            children=[self.view],
            style_classes=["left"]
            if data.DOCK_POSITION == "Left"
            else ["right"]
            if data.DOCK_POSITION == "Right"
            else [],
        )

        self.wrapper.set_orientation(dock_wrapper_orientation_val)
        self.view.set_orientation(dock_wrapper_orientation_val)

        if dock_wrapper_orientation_val == Gtk.Orientation.VERTICAL:
            self.wrapper.add_style_class("vertical")
        else:
            self.wrapper.remove_style_class("vertical")

        match data.DOCK_THEME:
            case "Pills":
                self.wrapper.add_style_class("pills")
            case "Dense":
                self.wrapper.add_style_class("dense")
            case "Edge":
                self.wrapper.add_style_class("edge")
            case _:
                self.wrapper.add_style_class("pills")

        self.dock_eventbox = EventBox()
        self.dock_eventbox.add(self.wrapper)
        self.dock_eventbox.connect("enter-notify-event", self._on_dock_enter)
        self.dock_eventbox.connect("leave-notify-event", self._on_dock_leave)

        # Create components using DockComponents
        self.components = DockComponents(
            orientation_val="h" if not data.VERTICAL else "v", dock_instance=self
        )

        # Add components based on position
        if self.actual_dock_is_horizontal:  # Bottom dock
            self.view.add(self.components)
        elif data.DOCK_POSITION == "Left":
            self.view.add(self.components)
        else:  # Right position
            self.view.add(self.components)

        self.corner_left = Box()
        self.corner_right = Box()
        self.corner_top = Box()
        self.corner_bottom = Box()

        if self.actual_dock_is_horizontal:
            self.corner_left = Box(
                name="dock-corner-left",
                orientation=Gtk.Orientation.VERTICAL,
                h_align="start",
                children=[Box(v_expand=True, v_align="fill"), MyCorner("bottom-right")],
            )
            self.corner_right = Box(
                name="dock-corner-right",
                orientation=Gtk.Orientation.VERTICAL,
                h_align="end",
                children=[Box(v_expand=True, v_align="fill"), MyCorner("bottom-left")],
            )
            self.dock_full = Box(
                name="dock-full",
                orientation=Gtk.Orientation.HORIZONTAL,
                h_expand=True,
                h_align="fill",
                children=[self.corner_left, self.dock_eventbox, self.corner_right],
            )
        else:
            if anchor_to_set == "right":
                self.corner_top = Box(
                    name="dock-corner-top",
                    orientation=Gtk.Orientation.HORIZONTAL,
                    v_align="start",
                    children=[
                        Box(h_expand=True, h_align="fill"),
                        MyCorner("bottom-right"),
                    ],
                )
                self.corner_bottom = Box(
                    name="dock-corner-bottom",
                    orientation=Gtk.Orientation.HORIZONTAL,
                    v_align="end",
                    children=[
                        Box(h_expand=True, h_align="fill"),
                        MyCorner("top-right"),
                    ],
                )
            else:
                self.corner_top = Box(
                    name="dock-corner-top",
                    orientation=Gtk.Orientation.HORIZONTAL,
                    v_align="start",
                    children=[
                        MyCorner("bottom-left"),
                        Box(h_expand=True, h_align="fill"),
                    ],
                )
                self.corner_bottom = Box(
                    name="dock-corner-bottom",
                    orientation=Gtk.Orientation.HORIZONTAL,
                    v_align="end",
                    children=[MyCorner("top-left"), Box(h_expand=True, h_align="fill")],
                )

            self.dock_full = Box(
                name="dock-full",
                orientation=Gtk.Orientation.VERTICAL,
                v_expand=True,
                v_align="fill",
                margin=0,  # Add explicit margin=0
                children=[self.corner_top, self.dock_eventbox, self.corner_bottom],
            )

        self.dock_revealer = Revealer(
            name="dock-revealer",
            transition_type=revealer_transition_type,
            transition_duration=250,
            child_revealed=False,
            child=self.dock_full,
        )

        self.hover_activator = EventBox()

        # Adjust hover activator size based on position and dock position
        if self.actual_dock_is_horizontal:
            # Bottom dock
            self.hover_activator.set_size_request(-1, 1)
        else:
            # Vertical dock (Left or Right)
            self.hover_activator.set_size_request(1, -1)

        self.hover_activator.connect("enter-notify-event", self._on_hover_enter)
        self.hover_activator.connect("leave-notify-event", self._on_hover_leave)

        # Create main box with correct child order based on position
        if self.actual_dock_is_horizontal:
            # Bottom dock
            self.main_box = Box(
                orientation=main_box_orientation_val,
                children=[self.hover_activator, self.dock_revealer],
                h_align=main_box_h_align_val,
            )
        else:
            # Vertical dock
            if data.DOCK_POSITION == "Left":
                # Left dock - revealer first, then hover activator
                self.main_box = Box(
                    orientation=main_box_orientation_val,
                    children=[self.dock_revealer, self.hover_activator],
                    h_align=main_box_h_align_val,
                )
            else:
                # Right dock - hover activator first, then revealer
                self.main_box = Box(
                    orientation=main_box_orientation_val,
                    children=[self.hover_activator, self.dock_revealer],
                    h_align=main_box_h_align_val,
                )
        self.add(self.main_box)

        if data.DOCK_THEME in ["Edge", "Dense"]:
            for corner in [
                self.corner_left,
                self.corner_right,
                self.corner_top,
                self.corner_bottom,
            ]:
                corner.set_visible(False)

        if not data.DOCK_ENABLED:
            self.set_visible(False)

        if self.always_occluded:
            self.dock_full.add_style_class("occluded")

        if self.conn.ready:
            GLib.timeout_add(250, self.check_occlusion_state)
        else:
            self.conn.connect(
                "event::ready",
                lambda *args: GLib.timeout_add(250, self.check_occlusion_state),
            )

        self.conn.connect("event::workspace", self.check_hide)

        GLib.timeout_add_seconds(1, self.check_config_change)

    def _on_hover_enter(self, *args):
        self.is_mouse_over_dock_area = True
        if self.hide_id:
            GLib.source_remove(self.hide_id)
            self.hide_id = None
        self.dock_revealer.set_reveal_child(True)
        if not self.always_occluded:
            self.dock_full.remove_style_class("occluded")

    def _on_hover_leave(self, *args):
        self.is_mouse_over_dock_area = False
        self.delay_hide()

    def _on_dock_enter(self, widget, event):
        self.is_mouse_over_dock_area = True
        if self.hide_id:
            GLib.source_remove(self.hide_id)
            self.hide_id = None
        self.dock_revealer.set_reveal_child(True)
        if not self.always_occluded:
            self.dock_full.remove_style_class("occluded")
        return True

    def _on_dock_leave(self, widget, event):
        if event.detail == Gdk.NotifyType.INFERIOR:
            return False

        self.is_mouse_over_dock_area = False
        self.delay_hide()

        if self.always_occluded:
            self.dock_full.add_style_class("occluded")
        return True

    def delay_hide(self):
        if self.hide_id:
            GLib.source_remove(self.hide_id)
        self.hide_id = GLib.timeout_add(250, self.hide_dock_if_not_hovered)

    def hide_dock_if_not_hovered(self):
        self.hide_id = None
        if (
            not self.is_mouse_over_dock_area
            and not self._drag_in_progress
            and not self._prevent_occlusion
        ):
            if self.always_occluded:
                self.dock_revealer.set_reveal_child(False)
            else:
                occlusion_region = (
                    ("bottom", self.effective_occlusion_size)
                    if self.actual_dock_is_horizontal
                    else ("right", self.effective_occlusion_size)
                )
                if check_occlusion(occlusion_region) or not self.view.get_children():
                    self.dock_revealer.set_reveal_child(False)
        return False

    def check_hide(self, *args):
        if (
            self.is_mouse_over_dock_area
            or self._drag_in_progress
            or self._prevent_occlusion
        ):
            return

        clients = self.get_clients()
        current_ws = self.get_workspace()
        ws_clients = [w for w in clients if w["workspace"]["id"] == current_ws]

        if not self.always_occluded:
            if not ws_clients:
                if not self.dock_revealer.get_reveal_child():
                    self.dock_revealer.set_reveal_child(True)
                self.dock_full.remove_style_class("occluded")
            elif any(
                not w.get("floating") and not w.get("fullscreen") for w in ws_clients
            ):
                self.check_occlusion_state()
            else:
                if not self.dock_revealer.get_reveal_child():
                    self.dock_revealer.set_reveal_child(True)
                self.dock_full.remove_style_class("occluded")
        else:
            if self.dock_revealer.get_reveal_child():
                self.dock_revealer.set_reveal_child(False)
            self.dock_full.add_style_class("occluded")

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

    def check_occlusion_state(self):
        if (
            self.is_mouse_over_dock_area
            or self._drag_in_progress
            or self._prevent_occlusion
        ):
            if not self.dock_revealer.get_reveal_child():
                self.dock_revealer.set_reveal_child(True)
            if not self.always_occluded:
                self.dock_full.remove_style_class("occluded")
            return True

        if not data.DOCK_AUTO_HIDE:
            if not self.dock_revealer.get_reveal_child():
                self.dock_revealer.set_reveal_child(True)
            if not self.always_occluded:
                self.dock_full.remove_style_class("occluded")
            return True

        if self.always_occluded:
            if self.dock_revealer.get_reveal_child():
                self.dock_revealer.set_reveal_child(False)
            self.dock_full.add_style_class("occluded")
            return True

        occlusion_region = (
            ("bottom", self.effective_occlusion_size)
            if self.actual_dock_is_horizontal
            else ("right", self.effective_occlusion_size)
        )
        is_occluded_by_window = check_occlusion(occlusion_region)
        is_empty = not self.view.get_children()

        if is_occluded_by_window or is_empty:
            if self.dock_revealer.get_reveal_child():
                self.dock_revealer.set_reveal_child(False)
            self.dock_full.add_style_class("occluded")
        else:
            if not self.dock_revealer.get_reveal_child():
                self.dock_revealer.set_reveal_child(True)
            self.dock_full.remove_style_class("occluded")

        return True

    def _update_size(self):
        width, _ = self.view.get_preferred_width()
        self.set_size_request(width, -1)
        return False

    def check_config_change(self):
        new_always_occluded = data.DOCK_ALWAYS_OCCLUDED
        if self.always_occluded != new_always_occluded:
            self.always_occluded = new_always_occluded
            self.check_occlusion_state()
        return True

    def check_config_change_immediate(self):
        previous_always_occluded = self.always_occluded
        self.always_occluded = data.DOCK_ALWAYS_OCCLUDED

        if previous_always_occluded != self.always_occluded:
            self.check_occlusion_state()
        return False

    @staticmethod
    def notify_config_change():
        for dock_instance in Dock._instances:
            GLib.idle_add(dock_instance.check_config_change_immediate)

    @staticmethod
    def update_visibility(visible):
        for dock in Dock._instances:
            dock.set_visible(visible)
            if visible:
                GLib.idle_add(dock.check_occlusion_state)
            else:
                if (
                    hasattr(dock, "dock_revealer")
                    and dock.dock_revealer.get_reveal_child()
                ):
                    dock.dock_revealer.set_reveal_child(False)

    def on_app_drag_begin(self):
        """Called when application drag begins"""
        self._drag_in_progress = True
        # Ensure dock is visible during drag
        self.dock_revealer.set_reveal_child(True)
        if not self.always_occluded:
            self.dock_full.remove_style_class("occluded")

    def on_app_drag_end(self):
        """Called when application drag ends"""
        self._drag_in_progress = False
        # Check if we should hide the dock
        GLib.idle_add(self.check_occlusion_state)

    def prevent_hiding(self, prevent=True):
        """Prevent the dock from hiding"""
        self._prevent_occlusion = prevent
        if prevent:
            # Force dock to be visible
            self.dock_revealer.set_reveal_child(True)
            if not self.always_occluded:
                self.dock_full.remove_style_class("occluded")
        else:
            # Check if we should hide
            GLib.idle_add(self.check_occlusion_state)
