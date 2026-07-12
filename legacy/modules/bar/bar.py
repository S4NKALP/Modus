from fabric.hyprland.widgets import HyprlandLanguage, get_hyprland_connection
from fabric.hyprland.service import HyprlandEvent
from fabric.system_tray.widgets import SystemTray
from fabric.widgets.shapes import Corner
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.datetime import DateTime
from fabric.widgets.label import Label
from utils.wayland import WaylandWindow as Window
from modules.bar.components import Metrics, workspace, SystemIndicators, UpdatesWidget
import config.data as data
from gi.repository import Gdk, GLib
import utils.icons as icons
import os
import json


class Bar(Window):
    def __init__(self, **kwargs):
        super().__init__(
            name="bar",
            layer="top",
            anchor="left top right"
            if not data.VERTICAL and not data.BOTTOM_BAR
            else "top right bottom"
            if data.VERTICAL and data.VERTICAL_RIGHT_ALIGN
            else "top left bottom"
            if data.VERTICAL
            else "bottom left right",
            exclusivity="auto",
            visible=True,
            all_visible=True,
        )

        self.launcher = kwargs.get("launcher", None)
        self.component_visibility = data.BAR_COMPONENTS_VISIBILITY

        # Determine if we should use vertical layout for components
        is_vertical_layout = data.VERTICAL

        self.workspaces = Button(
            child=workspace,
            name="workspaces",
        )

        self.connection = get_hyprland_connection()
        self.tray = SystemTray(
            name="tray",
            spacing=4,
            icon_size=16,
            orientation="h" if not is_vertical_layout else "v",
        )

        self.date_time = Button(
            name="datetime",
            child=DateTime(
                formatters=["%-I:%M:%p 󰧞 %a %d %b"]
                if not is_vertical_layout
                else ["%I\n%M\n%p"],
                h_align="center" if not is_vertical_layout else "fill",
                v_align="center",
            ),
            on_clicked=lambda *_: self.calendar(),
        )
        self.date_time.connect("enter_notify_event", self.on_button_enter)
        self.date_time.connect("leave_notify_event", self.on_button_leave)

        self.button_app = Button(
            name="button-bar",
            child=Label(name="button-bar-label", markup=icons.apps),
            on_clicked=lambda *_: self.search_apps(),
        )
        self.button_app.connect("enter_notify_event", self.on_button_enter)
        self.button_app.connect("leave_notify_event", self.on_button_leave)

        self.updates = UpdatesWidget()
        self.updates.connect("enter_notify_event", self.on_button_enter)
        self.updates.connect("leave_notify_event", self.on_button_leave)

        self.lang_label = Label(name="lang-label")
        self.language = Button(
            name="language", h_align="center", v_align="center", child=self.lang_label
        )
        self.on_language_switch()
        self.connection.connect("event::activelayout", self.on_language_switch)

        self.metrics = Metrics()
        self.indicators = SystemIndicators(launcher=self.launcher)

        self.applets = Box(
            name="system-indicator",
            spacing=4,
            orientation="h" if not is_vertical_layout else "v",
            children=[self.language, self.indicators],
        )

        # Apply visibility settings to components
        self.apply_component_visibility()

        self.h_start_children = [self.button_app, self.updates]

        self.h_center_children = [
            self.date_time,
            self.workspaces,
            self.metrics,
            self.applets,
        ]

        self.h_end_children = [self.tray]

        self.v_start_children = [
            self.button_app,
            self.updates,
            self.workspaces,
            self.metrics,
        ]
        self.v_end_children = [self.tray, self.applets, self.date_time]

        self.v_all_children = []
        self.v_all_children.extend(self.v_start_children)
        self.v_all_children.extend(self.v_end_children)

        # Use centered layout when both vertical and centered_bar are enabled
        is_centered_bar = is_vertical_layout and getattr(data, "CENTERED_BAR", False)

        self.bar = CenterBox(
            name="bar",
            orientation="h" if not is_vertical_layout else "v",
            h_align="fill",
            v_align="fill",
            start_children=None
            if is_centered_bar
            else Box(
                name="start-container",
                spacing=4,
                orientation="h" if not is_vertical_layout else "v",
                children=self.h_start_children
                if not is_vertical_layout
                else self.v_start_children,
            ),
            center_children=Box(
                orientation="v",
                spacing=4,
                children=self.v_all_children
                if is_centered_bar
                else Box(
                    name="center-container",
                    spacing=4,
                    orientation="h" if not is_vertical_layout else "v",
                    children=self.h_center_children if not is_vertical_layout else None,
                ),
            )
            if is_vertical_layout
            else Box(
                name="center-container",
                spacing=4,
                orientation="h" if not is_vertical_layout else "v",
                children=self.h_center_children if not is_vertical_layout else None,
            ),
            end_children=None
            if is_centered_bar
            else Box(
                name="end-container",
                spacing=4,
                orientation="h" if not is_vertical_layout else "v",
                children=self.h_end_children
                if not is_vertical_layout
                else self.v_end_children,
            ),
        )

        self.children = self.bar

    def apply_component_visibility(self):
        """Apply saved visibility settings to all components"""
        components = {
            "metrics": self.metrics,
            "indicators": self.applets,
            "updates": self.updates,
            "workspaces": self.workspaces,
            "button_app": self.button_app,
            # "button_tools": self.button_tools,
            "language": self.language,
            "date_time": self.date_time,
            "tray": self.tray,
        }

        for component_name, widget in components.items():
            if component_name in self.component_visibility:
                widget.set_visible(self.component_visibility[component_name])

    def toggle_component_visibility(self, component_name):
        """Toggle visibility for a specific component"""
        components = {
            "metrics": self.metrics,
            "indicators": self.applets,
            "updates": self.updates,
            "workspaces": self.workspaces,
            "button_app": self.button_app,
            # "button_tools": self.button_tools,
            "language": self.language,
            "date_time": self.date_time,
            "tray": self.tray,
        }

        if component_name in components and component_name in self.component_visibility:
            # Toggle the visibility state
            self.component_visibility[component_name] = not self.component_visibility[
                component_name
            ]
            # Apply the new state
            components[component_name].set_visible(
                self.component_visibility[component_name]
            )

            # Update the configuration
            config_file = os.path.expanduser(
                f"~/{data.APP_NAME}/config/assets/config.json"
            )
            try:
                if os.path.exists(config_file):
                    with open(config_file, "r") as f:
                        config = json.load(f)

                    # Update the config with the new visibility state
                    config[f"bar_{component_name}_visible"] = self.component_visibility[
                        component_name
                    ]

                    # Write the updated config back to file
                    with open(config_file, "w") as f:
                        json.dump(config, f, indent=4)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error updating config file: {e}")
                # Revert the visibility change if config update fails
                self.component_visibility[
                    component_name
                ] = not self.component_visibility[component_name]
                components[component_name].set_visible(
                    self.component_visibility[component_name]
                )

            return self.component_visibility[component_name]

        return None

    def on_button_enter(self, widget, event):
        window = widget.get_window()
        if window:
            window.set_cursor(Gdk.Cursor(Gdk.CursorType.HAND2))

    def on_button_leave(self, widget, event):
        window = widget.get_window()
        if window:
            window.set_cursor(None)

    def search_apps(self):
        self.launcher.open("launcher")

    def calendar(self):
        self.launcher.open("calendar")

    def on_language_switch(self, _=None, event: HyprlandEvent = None):
        lang = event.data[1] if event else HyprlandLanguage().get_label()
        self.language.set_tooltip_text(lang)
        if not data.VERTICAL:
            self.lang_label.set_label(lang[:2].lower())
        else:
            self.lang_label.add_style_class("icon")
            self.lang_label.set_markup(icons.keyboard)


class MyCorner(Box):
    def __init__(self, position):
        super().__init__(
            name="corner-container",
            children=Corner(
                name="corner",
                orientation=position,
                size=20,
            ),
        )


class Corners(Window):
    def __init__(self):
        super().__init__(
            layer="top",
            anchor="top left bottom right",
            pass_through=True,
            child=Box(
                orientation="vertical",
                children=[
                    Box(
                        children=[
                            MyCorner("top-left"),
                            Box(h_expand=True),
                            MyCorner("top-right"),
                        ]
                    ),
                    Box(v_expand=True),
                    Box(
                        children=[
                            MyCorner("bottom-left"),
                            Box(h_expand=True),
                            MyCorner("bottom-right"),
                        ]
                    ),
                ],
            ),
        )
