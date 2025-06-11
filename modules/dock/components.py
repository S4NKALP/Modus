import os
import json
import config.data as data
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.datetime import DateTime
from fabric.system_tray.widgets import SystemTray
from modules.dock.battery import Battery
from modules.dock.metrics import Metrics
from modules.dock.controls import Controls
from modules.dock.workspaces import workspace
from modules.dock.indicators import Indicators
from modules.dock.applications import Applications


class DockComponents(Box):
    def __init__(self, orientation_val="h", dock_instance=None, **kwargs):
        super().__init__(
            name="dock-components",
            orientation=orientation_val,
            spacing=8,
            **kwargs
        )
        
        self.dock_instance = dock_instance
        
        # Create applications with dock reference
        self.applications = Applications(
            orientation_val=orientation_val,
            dock_instance=dock_instance
        )
        
        # Initialize component visibility from data
        self.component_visibility = data.DOCK_COMPONENTS_VISIBILITY

        # Create components
        self.workspaces = Button(
            child=workspace,
            name="workspaces",
        )
        self.metrics = Metrics()
        self.battery = Battery()
        self.date_time = DateTime(
            name="date-time",
            formatters=["%I:%M"] if not data.VERTICAL else ["%I\n%M"],
            h_align="center" if not data.VERTICAL else "fill",
            v_align="center",
            h_expand=True,
            v_expand=True,
        )
        self.controls = Controls()
        self.indicators = Indicators()
        self.systray = SystemTray(
            icon_size=18,
            spacing=4,
            name="tray",
            orientation="h" if not data.VERTICAL else "v",
        )
        
        # Add methods to connect drag signals
        self.connect_drag_signals()
        
    def connect_drag_signals(self):
        # Method to connect drag signals from applications to parent
        pass
        
    def set_drag_callback(self, on_drag_begin_cb, on_drag_end_cb):
        """Set callbacks for drag operations from applications component"""
        # Connect to applications drag signals
        self.applications.connect("drag-begin", 
            lambda widget, context: on_drag_begin_cb())
        self.applications.connect("drag-end", 
            lambda widget, context: on_drag_end_cb())

        # Add components based on position
        if data.DOCK_POSITION == "Right":
            self.add(self.date_time)
            self.add(self.controls)
            self.add(self.indicators)
            self.add(self.applications)
            self.add(self.battery)
            self.add(self.metrics)
            self.add(self.workspaces)
            self.add(self.systray)
        else:  # Bottom or Left position
            self.add(self.workspaces)
            self.add(self.metrics)
            self.add(self.controls)
            self.add(self.applications)
            self.add(self.indicators)
            self.add(self.battery)
            self.add(self.date_time)
            self.add(self.systray)

        # Apply initial visibility
        self.apply_component_props()

    def apply_component_props(self):
        components = {
            "workspaces": self.workspaces,
            "metrics": self.metrics,
            "battery": self.battery,
            "date_time": self.date_time,
            "controls": self.controls,
            "indicators": self.indicators,
            "systray": self.systray,
            "applications": self.applications,
        }

        for component_name, widget in components.items():
            if component_name in self.component_visibility:
                widget.set_visible(self.component_visibility[component_name])

    def toggle_component_visibility(self, component_name):
        components = {
            "workspaces": self.workspaces,
            "metrics": self.metrics,
            "battery": self.battery,
            "date_time": self.date_time,
            "controls": self.controls,
            "indicators": self.indicators,
            "systray": self.systray,
            "applications": self.applications,
        }

        if component_name in components and component_name in self.component_visibility:
            self.component_visibility[component_name] = not self.component_visibility[
                component_name
            ]
            components[component_name].set_visible(
                self.component_visibility[component_name]
            )

            config_file = os.path.expanduser(
                f"~/.config/{data.APP_NAME}/config/config.json"
            )
            if os.path.exists(config_file):
                try:
                    with open(config_file, "r") as f:
                        config = json.load(f)

                    config[f"dock_{component_name}_visible"] = (
                        self.component_visibility[component_name]
                    )

                    with open(config_file, "w") as f:
                        json.dump(config, f, indent=4)
                except Exception as e:
                    print(f"Error updating config file: {e}")

            return self.component_visibility[component_name]

        return None
