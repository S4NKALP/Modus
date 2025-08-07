# Standard library imports
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

        # Set up auto-refresh timer for audio streams
        self._refresh_timer = GLib.timeout_add_seconds(2, self._auto_refresh)

    def _auto_refresh(self):
        """Auto-refresh the application list every 2 seconds"""
        self._populate_apps()
        return True  # Continue the timer

    def _go_back(self, *_):
        """Return to main control center view"""
        self.control_center.close_per_app_volume()

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

        # Use fabric audio service for applications
        if not audio_service:
            self._show_no_apps_message()
            return

        applications = getattr(audio_service, "applications", [])
        
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

    def _create_app_control(self, app):
        """Create volume control for a single application"""
        # Format and truncate app name
        app_name = self._format_app_name(app.name)
        if len(app_name) > 20:
            app_name = app_name[:17] + "..."

        # Get current volume from fabric audio service
        # Fabric returns volume as a float, typically 0.0 to max_volume (default 100)
        current_volume = getattr(app, "volume", 0.0)
        max_vol = getattr(audio_service, "max_volume", 100) if audio_service else 100
        
        # Ensure volume is in valid range
        volume_percent = max(0, min(current_volume, max_vol))

        # Volume scale - use fabric's max_volume as range
        volume_scale = Scale(
            value=volume_percent,
            min_value=0,
            max_value=max_vol,
            increments=(1, 5),
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

    def _set_app_volume(self, app, volume_value):
        """Set volume for a specific application using fabric audio service"""
        if app.name in self._updating_volumes:
            return

        self._updating_volumes.add(app.name)

        try:
            # Get max volume from audio service
            max_vol = getattr(audio_service, "max_volume", 100) if audio_service else 100
            
            # Ensure volume is within bounds
            volume_value = max(0, min(volume_value, max_vol))
            
            # Set volume directly - fabric expects the actual volume value, not percentage
            app.volume = volume_value
            
        except Exception as e:
            print(f"Error setting volume for {app.name}: {e}")
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

        # Disconnect fabric audio service signals
        if audio_service:
            for connection in self._signal_connections:
                try:
                    audio_service.disconnect(connection)
                except:
                    pass

        self._signal_connections.clear()
        self._app_widgets.clear()
        self._updating_volumes.clear()

        super().destroy()

