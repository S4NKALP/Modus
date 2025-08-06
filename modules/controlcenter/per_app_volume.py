# Standard library imports
import subprocess
from gi.repository import GLib

# Fabric imports
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from fabric.widgets.scale import Scale
from fabric.widgets.scrolledwindow import ScrolledWindow

# Local imports
from utils.roam import audio_service


class PerAppVolumeControl(Box):
    """Per-application volume control widget"""

    def __init__(self, control_center, **kwargs):
        super().__init__(
            orientation="vertical",
            name="per-app-volume-control",
            style_classes="menu",
            spacing=5,
            **kwargs,
        )

        self.control_center = control_center
        self._updating_volumes = set()
        self._app_widgets = {}
        self._signal_connections = []

        # Header with back button (hidden for cleaner UI)

        # Scrollable container for app volume controls
        self.apps_container = Box(
            orientation="vertical",
            name="apps-scrolled-container",
            spacing=5,
        )

        self.scrolled_window = ScrolledWindow(
            name="apps-scrolled-window",
            child=self.apps_container,
            size=(300, 500),
        )

        # Add escape key binding for navigation back
        try:
            if hasattr(self.control_center, "add_keybinding"):
                self.control_center.add_keybinding("Escape", self._go_back)
        except Exception:
            pass  # Ignore if keybinding fails

        self.children = [self.scrolled_window]

        # Connect to audio service changes
        if audio_service:
            self._signal_connections.append(
                audio_service.connect("stream-added", self._on_stream_changed)
            )
            self._signal_connections.append(
                audio_service.connect("stream-removed", self._on_stream_changed)
            )

        # Initial population
        self._populate_apps()

        # Set up auto-refresh timer for PulseAudio sinks
        self._refresh_timer = GLib.timeout_add_seconds(2, self._auto_refresh)

    def _auto_refresh(self):
        """Auto-refresh the application list every 2 seconds"""
        self._populate_apps()
        return True  # Continue the timer

    def _go_back(self, *_):
        """Return to main control center view"""
        self.control_center.close_per_app_volume()

    def _get_pulse_sinks(self):
        """Get PulseAudio sink inputs (application audio streams)"""
        try:
            result = subprocess.run(
                ["pactl", "list", "sink-inputs"],
                capture_output=True,
                text=True,
                check=True,
            )

            sinks = []
            current_sink = {}

            for line in result.stdout.split("\n"):
                line = line.strip()

                if line.startswith("Sink Input #"):
                    if current_sink:
                        sinks.append(current_sink)
                    current_sink = {
                        "index": line.split("#")[1],
                        "name": "Unknown",
                        "volume_raw": 100,
                    }
                elif "application.name = " in line:
                    current_sink["name"] = line.split("= ")[1].strip('"')
                elif "Volume:" in line and "front-left:" in line:
                    parts = line.split()
                    for part in parts:
                        if part.endswith("%"):
                            current_sink["volume_raw"] = int(part.replace("%", ""))
                            break

            if current_sink:
                sinks.append(current_sink)

            return sinks

        except (subprocess.CalledProcessError, FileNotFoundError):
            return []

    def _format_app_name(self, name):
        """Format application name with proper capitalization"""
        if not name:
            return "Unknown"

        # Handle common app names specially
        special_names = {
            "spotify": "Spotify",
            "firefox": "Firefox",
            "chromium": "Chromium",
            "chrome": "Chrome",
            "vlc": "VLC",
            "discord": "Discord",
            "steam": "Steam",
            "zen": "Zen Browser",
            "code": "VS Code",
            "telegram": "Telegram",
        }

        name_lower = name.lower()
        if name_lower in special_names:
            return special_names[name_lower]

        # Default: capitalize first letter
        return name.capitalize()

    def _populate_apps(self):
        """Populate the widget with current audio applications"""
        # Clear existing widgets
        self.apps_container.children = []
        self._app_widgets.clear()

        # Try Fabric audio service first
        applications = []
        if audio_service and hasattr(audio_service, "applications"):
            applications = audio_service.applications

        # If no Fabric applications, try PulseAudio directly
        if not applications:
            pulse_sinks = self._get_pulse_sinks()

            if pulse_sinks:
                for sink in pulse_sinks:
                    app_widget = self._create_pulse_app_control(sink)
                    self.apps_container.children = list(
                        self.apps_container.children
                    ) + [app_widget]
                    self._app_widgets[sink["name"]] = (app_widget, sink)
                return

        # Use Fabric applications if available
        if applications:
            for app in applications:
                if hasattr(app, "name") and hasattr(app, "volume"):
                    app_widget = self._create_app_control(app)
                    self.apps_container.children = list(
                        self.apps_container.children
                    ) + [app_widget]
                    self._app_widgets[app.name] = (app_widget, app)
        else:
            self._show_no_apps_message()

    def _show_no_apps_message(self):
        """Show message when no apps are playing audio"""
        message = Label(
            label="No applications currently using audio",
            style_classes="subtitle",
            h_align="center",
            v_align="center",
        )
        self.apps_container.children = [message]

    def _create_pulse_app_control(self, sink):
        """Create volume control for a PulseAudio sink input"""
        # Format and truncate app name
        app_name = self._format_app_name(sink["name"])
        if len(app_name) > 20:
            app_name = app_name[:17] + "..."

        # Volume scale with Apple-like styling
        volume_scale = Scale(
            value=sink["volume_raw"],
            min_value=0,
            max_value=150,
            increments=(5, 5),
            name="apple-volume-slider",
            size=28,
            h_expand=True,
        )

        # Connect volume change handler
        volume_scale.connect(
            "change-value",
            lambda scale, scroll_type, value, sink_data=sink: self._set_pulse_volume(
                sink_data, value
            ),
        )

        # Create the app control widget
        app_control = Box(
            orientation="vertical",
            spacing=8,
            style_classes="apple-app-volume-item",
            children=[
                Label(
                    label=app_name,
                    style_classes="apple-app-name",
                    h_align="start",
                ),
                volume_scale,
            ],
        )

        return app_control

    def _create_app_control(self, app):
        """Create volume control for a single application (Fabric)"""
        # Format and truncate app name
        app_name = self._format_app_name(app.name)
        if len(app_name) > 20:
            app_name = app_name[:17] + "..."

        # Handle different volume formats
        volume_value = app.volume
        if isinstance(volume_value, float):
            if 0.0 <= volume_value <= 1.0:
                volume_percent = volume_value * 100
            else:
                volume_percent = min(max(volume_value, 0), 100)
        elif isinstance(volume_value, int):
            if volume_value <= 1:
                volume_percent = volume_value * 100
            else:
                volume_percent = min(max(volume_value, 0), 100)
        else:
            volume_percent = 50

        # Volume scale with Apple-like styling
        volume_scale = Scale(
            value=volume_percent,
            min_value=0,
            max_value=100,
            increments=(5, 5),
            name="apple-volume-slider",
            size=28,
            h_expand=True,
        )

        # Connect volume change handler
        volume_scale.connect(
            "change-value",
            lambda scale, scroll_type, value, app=app: self._set_app_volume(app, value),
        )

        # Create the app control widget
        app_control = Box(
            orientation="vertical",
            spacing=8,
            style_classes="apple-app-volume-item",
            children=[
                Label(
                    label=app_name,
                    style_classes="apple-app-name",
                    h_align="start",
                ),
                volume_scale,
            ],
        )

        return app_control

    def _set_pulse_volume(self, sink, volume_percent):
        """Set volume for a PulseAudio sink input"""
        if sink["name"] in self._updating_volumes:
            return

        self._updating_volumes.add(sink["name"])

        try:
            subprocess.run(
                [
                    "pactl",
                    "set-sink-input-volume",
                    sink["index"],
                    f"{int(volume_percent)}%",
                ],
                check=True,
            )
        except subprocess.CalledProcessError:
            pass
        finally:
            GLib.timeout_add(100, lambda: self._updating_volumes.discard(sink["name"]))

    def _set_app_volume(self, app, volume_percent):
        """Set volume for a specific application (Fabric)"""
        if app.name in self._updating_volumes:
            return

        self._updating_volumes.add(app.name)

        try:
            current_volume = app.volume

            if isinstance(current_volume, float):
                if 0.0 <= current_volume <= 1.0:
                    volume_value = volume_percent / 100.0
                else:
                    volume_value = volume_percent
            elif isinstance(current_volume, int):
                if current_volume <= 1:
                    volume_value = int(volume_percent / 100.0)
                else:
                    volume_value = int(volume_percent)
            else:
                volume_value = volume_percent

            app.volume = volume_value
        except Exception:
            pass
        finally:
            GLib.timeout_add(100, lambda: self._updating_volumes.discard(app.name))

    def _on_stream_changed(self, *_):
        """Handle when audio streams are added or removed"""
        GLib.idle_add(self._populate_apps)

    def refresh(self):
        """Manually refresh the application list"""
        self._populate_apps()

    def destroy(self):
        """Clean up resources"""
        if hasattr(self, "_refresh_timer"):
            GLib.source_remove(self._refresh_timer)

        for connection in self._signal_connections:
            try:
                connection.disconnect()
            except:
                pass

        self._signal_connections.clear()
        self._app_widgets.clear()
        self._updating_volumes.clear()

        super().destroy()

