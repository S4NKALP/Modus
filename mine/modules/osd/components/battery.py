from fabric.utils import GLib
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.wayland import WaylandWindow as Window

from modules.osd.components.base import BaseOSDContainer
from services.battery import BatteryService


class BatteryOSDContainer(BaseOSDContainer):
    def __init__(self, window: Window, **kwargs):
        super().__init__(window, **kwargs)
        self.battery = BatteryService()
        self._initialized = False  # Track if initial setup is complete
        self._last_state = None
        self._last_percentage = None
        self._setup_specific_components()
        self._connect_specific_signals()

    def _setup_specific_components(self):
        self.icon = Image(icon_name="battery-symbolic", icon_size=26)
        self.label = Label()

        # Defer initialization to allow services to initialize
        GLib.timeout_add(100, self._initialize_state)

        self.children = self.icon, self.label

    def _connect_specific_signals(self):
        self.battery.connect("changed", self._on_battery_changed)

    def _initialize_state(self):
        """Initialize the battery state after component setup."""
        self._last_state = self.battery.get_property("State")
        self._last_percentage = self.battery.get_property("Percentage")
        self._update_battery_display()
        # Mark as initialized after initial state is set
        GLib.timeout_add(500, self._mark_initialized)
        return False

    def _mark_initialized(self):
        """Mark the component as fully initialized."""
        self._initialized = True
        return False

    def _on_battery_changed(self, *args):
        """Handle battery state changes."""
        if not self._initialized:
            return

        if not self.is_hovered():
            current_state = self.battery.get_property("State")
            current_percentage = self.battery.get_property("Percentage")

            # Only show OSD for meaningful changes
            should_show = False

            # State changes (charging/discharging/full)
            if current_state != self._last_state:
                should_show = True

            # Battery level warnings (crossing thresholds)
            elif current_percentage is not None and self._last_percentage is not None:
                # Show on low battery (crossing 20% threshold going down)
                if (
                    self._last_percentage > 20
                    and current_percentage <= 20
                    or self._last_percentage > 98
                    and current_percentage <= 10
                    or self._last_percentage < 100
                    and current_percentage >= 100
                ):
                    should_show = True

            self._last_state = current_state
            self._last_percentage = current_percentage

            if should_show:
                self._update_battery_display()
                self.show_battery_osd()

    def _update_battery_display(self):
        """Update display based on current battery state."""
        state = self.battery.get_property("State")
        percentage = self.battery.get_property("Percentage")
        icon_name = self.battery.get_property("IconName")

        if percentage is None:
            percentage = 0

        # Determine icon
        if icon_name:
            self.update_icon(icon_name)
        else:
            self.update_icon("battery-symbolic")

        # Format the label
        if state == 4:  # Fully charged
            self.update_label(f"Battery Full ({percentage:.0f}%)")
        elif state == 1:  # Charging
            self.update_label(f"Charging ({percentage:.0f}%)")
        elif percentage <= 10:
            self.update_label(f"Battery Critical ({percentage:.0f}%)")
        elif percentage <= 20:
            self.update_label(f"Battery Low ({percentage:.0f}%)")
        else:
            self.update_label(f"Battery: {percentage:.0f}%")

    def update_icon(self, icon_name: str):
        """Update the battery icon."""
        self.icon.set_from_icon_name(icon_name, 26)

    def update_label(self, text: str):
        """Update the battery label."""
        self.label.set_text(text)

    def show_battery_osd(self):
        """Trigger the OSD to show."""
        if self.osd:
            self.osd.show_battery_osd()
        else:
            self.update()

    def update(self, *_):
        """Override to update display before showing OSD."""
        self._update_battery_display()
        super().update()
