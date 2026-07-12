from fabric.hyprland.service import Hyprland, HyprlandEvent
from fabric.hyprland.widgets import HyprlandWorkspaces, WorkspaceButton
from fabric.system_tray.widgets import SystemTray
from fabric.utils import Gdk, GLib
from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.datetime import DateTime
from fabric.widgets.eventbox import EventBox
from fabric.widgets.revealer import Revealer
from fabric.widgets.wayland import WaylandWindow as Window

import config.data as data
from modules.panel.components import (
    Battery,
    TaskBar,
    apply_enhanced_system_tray,
)
from services import has_config_changed, on_config_change
from utils.corners import MyCorner
from utils.functions import is_special_workspace_id
from utils.occlusion import check_occlusion, is_mouse_in_region, get_screen_dimensions


def config_dependent(func):
    def wrapper(self, *args, **kwargs):
        return func(self, *args, **kwargs)

    wrapper._config_dependent = True
    return wrapper


class Panel(Window):
    def __init__(self, **kwargs):
        panel_autohide = data.DATA()["panel_autohide"]
        panel_position = data.DATA().get("panel_position") or "bottom"

        super().__init__(
            name="panel-window",
            layer="top",
            anchor=panel_position,
            exclusivity="auto" if not panel_autohide else "none",
            pass_through=False,
            visible=False,
            all_visible=False,
        )

        self.hide_id = None
        self.is_mouse_over_panel_area = False
        self.effective_occlusion_size = 40
        self.panel_position = panel_position

        # Set corner types based on position
        if panel_position == "top":
            corner_left_type = "top-right"
            corner_right_type = "top-left"
            # For top position, corner goes first (at top)
            corner_left_children = [
                MyCorner(corner_left_type),
                Box(v_expand=True, v_align="fill"),
            ]
            corner_right_children = [
                MyCorner(corner_right_type),
                Box(v_expand=True, v_align="fill"),
            ]
        else:  # bottom
            corner_left_type = "bottom-right"
            corner_right_type = "bottom-left"
            # For bottom position, corner goes last (at bottom)
            corner_left_children = [
                Box(v_expand=True, v_align="fill"),
                MyCorner(corner_left_type),
            ]
            corner_right_children = [
                Box(v_expand=True, v_align="fill"),
                MyCorner(corner_right_type),
            ]

        self.corner_left = Box(
            name="corner-left",
            orientation="v",
            h_align="start",
            children=corner_left_children,
        )
        self.corner_right = Box(
            name="corner-right",
            orientation="v",
            h_align="end",
            children=corner_right_children,
        )

        use_12hr = data.DATA()["datetime_12hrs"]
        formatter = "%a %-d %b %I:%M %P" if use_12hr else "%a %-d %b %H:%M"

        self.datetime = DateTime(
            name="date-time", formatters=[formatter], interval=30000
        )
        self.tray = SystemTray(name="panel-button", spacing=4, icon_size=20)
        apply_enhanced_system_tray(self.tray)
        self.battery = Battery()
        self.taskbar = TaskBar()
        self.taskbar.set_visibility_callback(self._rebuild_layout_from_config)
        self.workspaces = HyprlandWorkspaces(
            name="workspaces",
            spacing=4,
            buttons_factory=lambda ws_id: (
                None
                if (
                    data.DATA()["workspace_hide_special"]
                    and is_special_workspace_id(ws_id)
                )
                else WorkspaceButton(id=ws_id, label=str(ws_id))
            ),
        )

        self.items = Box()

        # Create panel CenterBox with position-based CSS class
        self.panel_centerbox = CenterBox(
            name="panel",
            center_children=self.items,
        )

        # Add CSS class for top position using GTK style context
        if panel_position == "top":
            self.panel_centerbox.get_style_context().add_class("panel-top")

        self.panel_content = Box(
            name="panel-container",
            orientation="h",
            h_expand=True,
            children=[
                self.corner_left,
                self.panel_centerbox,
                self.corner_right,
            ],
        )

        # Set revealer transition based on position
        transition = "slide-down" if panel_position == "top" else "slide-up"

        self.panel_revealer = Revealer(
            name="panel-revealer",
            transition_type=transition,
            transition_duration=350,
            child_revealed=False,
            child=self.panel_content,
        )

        self.hover_activator = EventBox(name="hover-activator")
        self.hover_activator.set_size_request(-1, 8)

        # Arrange children based on position
        if panel_position == "top":
            panel_children = [self.panel_revealer, self.hover_activator]
        else:  # bottom
            panel_children = [self.hover_activator, self.panel_revealer]

        self.main_container = Box(
            name="panel-main",
            orientation="v",
            children=panel_children,
        )

        self.event_box = EventBox(
            name="panel-event-box",
            child=self.main_container,
        )
        self.event_box.connect("enter-notify-event", self._on_mouse_enter)
        self.event_box.connect("leave-notify-event", self._on_mouse_leave)

        self.children = self.event_box

        self.battery.connect(
            "notify::visible", lambda *_: self._rebuild_layout_from_config()
        )

        self._rebuild_layout_from_config()
        on_config_change(self._on_config_change)
        self._update_panel_visibility()

        self.hyprland = Hyprland()
        self.hyprland.connect("event::openwindow", self._on_window_event)
        self.hyprland.connect("event::closewindow", self._on_window_event)
        self.hyprland.connect("event::movewindow", self._on_window_event)
        self.hyprland.connect("event::changefloatingmode", self._on_window_event)
        self.hyprland.connect("event::fullscreen", self._on_window_event)
        self.hyprland.connect("event::workspacev2", self._on_window_event)

        if panel_autohide:
            self.panel_revealer.set_reveal_child(False)
            self.check_occlusion_state()

    def _get_enabled_widgets(self):
        components = data.DATA()
        enabled_widgets = {
            "workspace": components["workspace"],
            "taskbar": components["taskbar"],
            "systray": components["systray"],
            "battery": components["battery"],
            "datetime": components["datetime"],
        }
        return enabled_widgets

    @config_dependent
    def _rebuild_layout_from_config(self):
        enabled_widgets = self._get_enabled_widgets()

        items = []
        if enabled_widgets["workspace"]:
            items.append(self.workspaces)
        if enabled_widgets["taskbar"]:
            items.append(self.taskbar)
        if enabled_widgets["systray"]:
            items.append(self.tray)
        if enabled_widgets["battery"]:
            items.append(self.battery)
        if enabled_widgets["datetime"]:
            items.append(self.datetime)

        filtered_items = [w for w in items if w.get_visible()]

        self.items.children = filtered_items

        if data.DATA()["panel_enabled"]:
            self.show_all()

    def _update_panel_visibility(self):
        panel_enabled = data.DATA()["panel_enabled"]
        self.set_visible(panel_enabled)

    def _on_mouse_enter(self, widget, event):
        self.is_mouse_over_panel_area = True
        if self.hide_id:
            GLib.source_remove(self.hide_id)
            self.hide_id = None
        if data.DATA()["panel_autohide"]:
            self.panel_revealer.set_reveal_child(True)
        return True

    def _on_mouse_leave(self, widget, event):
        if event.detail == Gdk.NotifyType.INFERIOR:
            return False
        self.is_mouse_over_panel_area = False
        if data.DATA()["panel_autohide"]:
            self.delay_hide()
        return True

    def delay_hide(self):
        if self.hide_id:
            GLib.source_remove(self.hide_id)
        self.hide_id = GLib.timeout_add(250, self.hide_panel_if_not_hovered)

    def hide_panel_if_not_hovered(self):
        self.hide_id = None
        if not self.is_mouse_over_panel_area:
            occlusion_region = (self.panel_position, self.effective_occlusion_size)
            if check_occlusion(occlusion_region):
                self.panel_revealer.set_reveal_child(False)
        return False

    def _on_window_event(self, _, event: HyprlandEvent):
        GLib.idle_add(self.check_occlusion_state)

    def check_occlusion_state(self):
        try:
            # Robust hover check as fallback for high refresh rate monitors
            # If GTK events were missed, we verify the mouse position manually
            if not self.is_mouse_over_panel_area:
                # Determine the region we care about for hover
                # If the panel is hidden, it's just the activator area
                # If shown, it's the whole panel area
                is_revealed = self.panel_revealer.get_reveal_child()
                size = (
                    48 if is_revealed else 8
                )  # Approximate panel height when revealed

                # Get current width of the panel to avoid full-width hover detection
                width = self.main_container.get_allocated_width()
                if width > 1:
                    screen_width, screen_height = get_screen_dimensions()
                    x = (screen_width - width) // 2
                    y = 0 if self.panel_position == "top" else screen_height - size
                    occlusion_region = (x, y, width, size)
                else:
                    occlusion_region = (self.panel_position, size)

                if is_mouse_in_region(occlusion_region):
                    self.is_mouse_over_panel_area = True
                    if self.hide_id:
                        GLib.source_remove(self.hide_id)
                        self.hide_id = None

            if self.is_mouse_over_panel_area:
                if not self.panel_revealer.get_reveal_child():
                    self.panel_revealer.set_reveal_child(True)
                return True

            if not data.DATA()["panel_autohide"]:
                if not self.panel_revealer.get_reveal_child():
                    self.panel_revealer.set_reveal_child(True)
                return True

            # Use actual width for occlusion check too
            width = self.main_container.get_allocated_width()
            if width > 1:
                screen_width, screen_height = get_screen_dimensions()
                x = (screen_width - width) // 2
                y = (
                    0
                    if self.panel_position == "top"
                    else screen_height - self.effective_occlusion_size
                )
                occlusion_region = (
                    x,
                    y,
                    width,
                    self.effective_occlusion_size,
                )
            else:
                occlusion_region = (self.panel_position, self.effective_occlusion_size)

            is_occluded_by_window = check_occlusion(occlusion_region)

            self.panel_revealer.set_reveal_child(not is_occluded_by_window)
        except Exception as e:
            from fabric.utils import logger

            logger.warning(f"Error in check_occlusion_state: {e}")

        return False

    @config_dependent
    def _on_config_change(self, new_config, old_config):
        config_paths = [
            "panel.enabled",
            "panel.autohide",
            "panel.position",
            "panel.systray.enabled",
            "panel.datetime.enabled",
            "panel.datetime.12hrs",
            "panel.workspace.enabled",
            "panel.workspace.hide_special_ws",
            "panel.taskbar.enabled",
            "panel.taskbar.icon_size",
            "panel.taskbar.hide_empty",
            "panel.taskbar.hide_special",
            "panel.battery.enabled",
            "panel.battery.label",
            "panel.battery.hide_on_full",
            "panel.battery.icon_size",
        ]

        config_changed = any(
            has_config_changed(old_config, new_config, path) for path in config_paths
        )

        if config_changed:
            # Check if position changed (requires application restart)
            new_position = data.DATA().get("panel_position") or "bottom"
            if new_position != self.panel_position:
                # Position change requires full restart due to Wayland limitations
                print("Panel position changed - restarting application...")
                import os
                import sys

                # Restart the Python script
                os.execv(sys.executable, ["python"] + sys.argv)
                return

            # Position didn't change, handle other config changes
            panel_autohide = data.DATA()["panel_autohide"]

            # Set exclusivity based on autohide setting
            exclusivity = "none" if panel_autohide else "auto"
            self.set_property("exclusivity", exclusivity)

            self._update_panel_visibility()

            use_12hr = data.DATA()["datetime_12hrs"]
            formatter = "%a %-d %b %I:%M %P" if use_12hr else "%a %-d %b %H:%M"
            self.datetime.formatters = [formatter]

            hide_special = data.DATA()["workspace_hide_special"]
            self.workspaces.buttons_factory = lambda ws_id: (
                None
                if (hide_special and is_special_workspace_id(ws_id))
                else WorkspaceButton(id=ws_id, label=str(ws_id))
            )

            self._rebuild_layout_from_config()

            if panel_autohide:
                self.check_occlusion_state()
