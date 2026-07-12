from fabric.widgets.box import Box
from fabric.widgets.wayland import WaylandWindow as Window

import config.data as data
from modules.osd.components import (
    AudioOSDContainer,
    BatteryOSDContainer,
    BrightnessOSDContainer,
    CapsLockOSDContainer,
    KeyboardLayoutOSDContainer,
    MicrophoneOSDContainer,
    NetworkOSDContainer,
)
from services import has_config_changed, on_config_change


class OSD(Box):
    def __init__(self, window: Window, **kwargs):
        super().__init__(orientation="h", name="osd", **kwargs)

        self.window = window
        self._load_config()

        # Container dictionary for easy access
        self.containers = {}
        self.current_container = None

        self._create_containers()
        self._setup_initial_container()
        self._connect_signals()

        on_config_change(self._on_config_change)

    def _create_containers(self):
        if self._audio_enabled:
            container = AudioOSDContainer(orientation="h", window=self.window)
            container.osd = self
            container.COOLDOWN_MS = self._cooldown_ms
            self.containers["audio"] = container

        if self._brightness_enabled:
            container = BrightnessOSDContainer(orientation="h", window=self.window)
            container.osd = self
            container.COOLDOWN_MS = self._cooldown_ms
            self.containers["brightness"] = container

        if self._capslock_enabled:
            container = CapsLockOSDContainer(orientation="h", window=self.window)
            container.osd = self
            container.COOLDOWN_MS = self._cooldown_ms
            self.containers["capslock"] = container

        if getattr(self, "_kb_layout_enabled", False):
            container = KeyboardLayoutOSDContainer(orientation="h", window=self.window)
            container.osd = self
            container.COOLDOWN_MS = self._cooldown_ms
            self.containers["kb_layout"] = container

        if getattr(self, "_network_enabled", False):
            container = NetworkOSDContainer(orientation="h", window=self.window)
            container.osd = self
            container.COOLDOWN_MS = self._cooldown_ms
            self.containers["network"] = container

        if getattr(self, "_microphone_enabled", False):
            container = MicrophoneOSDContainer(orientation="h", window=self.window)
            container.osd = self
            container.COOLDOWN_MS = self._cooldown_ms
            self.containers["microphone"] = container

        if getattr(self, "_battery_enabled", False):
            container = BatteryOSDContainer(orientation="h", window=self.window)
            container.osd = self
            container.COOLDOWN_MS = self._cooldown_ms
            self.containers["battery"] = container

    def _setup_initial_container(self):
        self.current_container = None
        self.children = []

    def _connect_signals(self):
        # All OSD containers (audio, brightness, capslock, keyboard_layout,
        # network, microphone) handle their signal connections internally
        # and call their respective show_*_osd() methods when needed.
        # No external signal connections are needed here.
        pass

    def _load_config(self):
        config = data.DATA()
        self._osd_enabled = config.get("osd")
        self._audio_enabled = config.get("osd_audio")
        self._brightness_enabled = config.get("osd_brightness")
        self._capslock_enabled = config.get("osd_capslock")
        self._kb_layout_enabled = config.get("osd_kb_layout")
        self._network_enabled = config.get("osd_network")
        self._microphone_enabled = config.get("osd_microphone")
        self._battery_enabled = config.get("osd_battery")
        self._cooldown_ms = config.get("osd_cooldown_ms")

    def _on_config_change(self, new_config, old_config):
        paths = [
            "osd",
            "osd_audio",
            "osd_brightness",
            "osd_capslock",
            "osd_kb_layout",
            "osd_network",
            "osd_microphone",
            "osd_battery",
            "osd_cooldown_ms",
            "osd_position",
        ]

        if any(has_config_changed(old_config, new_config, p) for p in paths):
            old_osd_enabled = self._osd_enabled
            old_audio_enabled = self._audio_enabled
            old_brightness_enabled = self._brightness_enabled
            old_capslock_enabled = self._capslock_enabled
            old_kb_layout_enabled = getattr(self, "_kb_layout_enabled", False)
            old_network_enabled = getattr(self, "_network_enabled", False)
            old_microphone_enabled = getattr(self, "_microphone_enabled", False)
            old_battery_enabled = getattr(self, "_battery_enabled", False)
            old_osd_position = getattr(self.window, "_current_osd_position", None)

            self._load_config()

            # Get current OSD position from config
            config = data.DATA()
            current_osd_position = config.get("osd_position") or "bottom"

            # Handle OSD position change by updating window properties
            if (
                old_osd_position is not None
                and old_osd_position != current_osd_position
            ):
                self.window._update_osd_position(current_osd_position)

            if old_osd_enabled != self._osd_enabled:
                self.window.set_visible(self._osd_enabled)

            if not self._osd_enabled:
                self.window.hide()
                return

            if (
                old_audio_enabled != self._audio_enabled
                or old_brightness_enabled != self._brightness_enabled
                or old_capslock_enabled != self._capslock_enabled
                or old_kb_layout_enabled != self._kb_layout_enabled
                or old_network_enabled != self._network_enabled
                or old_microphone_enabled != self._microphone_enabled
                or old_battery_enabled != self._battery_enabled
            ):
                # Clean up old containers
                for container in self.containers.values():
                    container.cleanup_all_handlers()

                self.containers.clear()

                self._create_containers()
                self._setup_initial_container()
                self._connect_signals()

    def _show_osd(self, container_type: str, enabled_flag: bool):
        container = self.containers.get(container_type)
        if not self._osd_enabled or not enabled_flag or not container:
            return

        if self.current_container != container_type:
            # Clean up previous container if it exists
            if self.current_container:
                prev_container = self.containers.get(self.current_container)
                if prev_container:
                    prev_container.cleanup_all_handlers()
                    prev_container.window.hide()

            self.current_container = container_type
            self.children = container
        container.update()

    def show_audio_osd(self):
        self._show_osd("audio", self._audio_enabled)

    def show_brightness_osd(self):
        self._show_osd("brightness", self._brightness_enabled)

    def show_capslock_osd(self):
        self._show_osd("capslock", self._capslock_enabled)

    def show_kb_layout_osd(self):
        self._show_osd("kb_layout", getattr(self, "_kb_layout_enabled", False))

    def show_network_osd(self):
        self._show_osd("network", getattr(self, "_network_enabled", False))

    def show_microphone_osd(self):
        self._show_osd("microphone", self._microphone_enabled)

    def show_battery_osd(self):
        self._show_osd("battery", getattr(self, "_battery_enabled", False))

    def toggle(self):
        if not self._osd_enabled:
            return

        if self.current_container:
            current_container = self.containers.get(self.current_container)
            if current_container:
                current_container.update()


class OSDWindow(Window):
    def __init__(self, **kwargs):
        # Load position config
        config = data.DATA()
        position = config.get("osd_position") or "bottom"

        # Set margin based on position
        if position == "top":
            margin = "40px 0px 0px 0px"
            anchor = "top"
        else:  # bottom (default)
            margin = "0px 0px 40px 0px"
            anchor = "bottom"

        super().__init__(
            name="osd-window",
            title="fabric-osd",
            anchor=anchor,
            margin=margin,
            child=OSD(window=self),
            visible=False,
            all_visible=False,
            **kwargs,
        )

        # Store current position for change detection
        self._current_osd_position = position

        self.build()

    def _update_osd_position(self, position):
        """Update OSD window position based on config change"""
        # Set margin based on position
        if position == "top":
            margin = "40px 0px 0px 0px"
            anchor = "top"
        else:  # bottom (default)
            margin = "0px 0px 40px 0px"
            anchor = "bottom"

        # Update window properties
        self.set_anchor(anchor)
        self.set_margin(margin)
        self._current_osd_position = position
