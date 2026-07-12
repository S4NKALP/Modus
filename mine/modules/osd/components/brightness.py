from fabric.widgets.image import Image
from fabric.widgets.scale import ScaleMark
from fabric.widgets.wayland import WaylandWindow as Window

from modules.osd.components.animated_scale import AnimatedScale
from modules.osd.components.base import BaseOSDContainer
from services import Brightness


class BrightnessOSDContainer(BaseOSDContainer):
    def __init__(self, window: Window, **kwargs):
        super().__init__(window, **kwargs)
        self.brightness = Brightness.get_initial()
        self._last_brightness = None  # Track to avoid duplicate updates
        self._setup_specific_components()
        self._connect_specific_signals()

    def _setup_specific_components(self):
        self.icon = Image(icon_name="display-brightness-symbolic", icon_size=26)

        current_brightness = self.brightness.screen_brightness
        brightness_percentage = (
            int((current_brightness / self.brightness.max_screen) * 100)
            if self.brightness.max_screen > 0
            else 50
        )

        self._last_brightness = brightness_percentage

        self.scale = AnimatedScale(
            marks=(ScaleMark(value=i) for i in range(1, 100, 10)),
            value=brightness_percentage,
            min_value=0,
            max_value=100,
            inverted=False,
            increments=(1, 1),
            orientation=self.get_orientation(),
            on_state_flags_changed=lambda sc, *_: (
                self.unfocus() if not (sc.get_state_flags() & 2) else None
            ),
            on_value_changed=lambda *_: self.is_hovered() and self._update_brightness(),
        )
        self.children = self.icon, self.scale

    def _connect_specific_signals(self):
        self.brightness.connect(
            "brightness_changed",
            self._on_brightness_changed,
        )

    def _on_brightness_changed(self, _, value):
        """Handle brightness changes from the service."""
        if self.is_hovered():
            # User is interacting with the slider, don't update
            return

        brightness_percentage = int((value / self.brightness.max_screen) * 100)

        # Only update if brightness actually changed
        if (
            self._last_brightness is None
            or abs(brightness_percentage - self._last_brightness) > 0
        ):
            self._last_brightness = brightness_percentage
            self._update_icon(brightness_percentage)
            self.scale.animate_value(brightness_percentage)
            self.show_brightness_osd()

    def show_brightness_osd(self):
        """Trigger the OSD to show the brightness container."""
        if self.osd:
            self.osd.show_brightness_osd()
        else:
            self.update()

    def _update_icon(self, brightness_percentage: int):
        """Update icon based on brightness level."""
        self.icon.set_from_icon_name(
            "display-brightness-high-symbolic"
            if brightness_percentage >= 80
            else "display-brightness-low-symbolic"
            if brightness_percentage < 50
            else "display-brightness-medium-symbolic",
            26,
        )

    def _update_brightness(self):
        """Update brightness when user drags the slider."""
        if self.is_hovered():
            new_brightness = int((self.scale.value / 100) * self.brightness.max_screen)
            self.brightness.screen_brightness = new_brightness
            self._last_brightness = int(self.scale.value)
            self._update_icon(int(self.scale.value))

    def update(self, *_):
        """Override to update display before showing OSD."""
        # Update the display before showing
        if self.brightness.screen_brightness is not None:
            brightness_percentage = int(
                (self.brightness.screen_brightness / self.brightness.max_screen) * 100
            )
            self._last_brightness = brightness_percentage
            self.scale.animate_value(brightness_percentage)
            self._update_icon(brightness_percentage)

        # Call parent's update to show the OSD
        super().update()
