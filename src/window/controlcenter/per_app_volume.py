from fabric.utils import GLib, logger
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.widgets.separator import Separator

from shared.widgets.flat_scale import FlatScale

# Local imports
from utils.roam import audio_service

# Mappings used to resolve an app's icon/display name from its description or
# name. Defined once at module level to avoid rebuilding on every refresh.
_APP_ICON_MAPPING = {
    "spotify": "spotify",
    "firefox": "firefox",
    "chromium": "chromium-browser",
    "chrome": "google-chrome",
    "vlc": "vlc",
    "discord": "discord",
    "steam": "steam",
    "zen": "zen-browser",
    "code": "vscode",
    "visual studio code": "vscode",
    "telegram": "telegram-desktop",
    "pulse": "audio-card",
    "pipewire": "audio-card",
    "alsa": "audio-card",
    "sink": "audio-speakers",
    "source": "audio-input-microphone",
    "youtube": "youtube",
    "music": "rhythmbox",
    "media": "multimedia-player",
}

_APP_SPECIAL_NAMES = {
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


class PerAppVolumeControl(Box):
    """Per-application volume control widget"""

    def __init__(self, control_center, **kwargs):
        super().__init__(
            orientation="vertical",
            name="per-app-volume-control",
            spacing=5,
            **kwargs,
        )

        self.control_center = control_center
        self._updating_volumes = set()
        self._app_widgets = {}
        self._signal_connections = []
        self._destroyed = False
        self._refresh_timer = None

        # Header with back button
        self.header = Box(
            orientation="horizontal",
            name="per-app-volume-header",
            style_classes="menu-header",
            children=[
                Button(
                    image=Image(icon_name="back", size=10),
                    on_clicked=lambda *_: self.control_center.close_per_app_volume(),
                ),
                Label("App Volume", name="app-volume-header"),
            ],
        )

        # Scrollable container for app volume controls
        self.apps_container = Box(
            orientation="vertical",
            name="apps-scrolled-container",
            spacing=2,
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
        except Exception as e:
            logger.error(f"An error occurred: {e}")  # Ignore if keybinding fails

        self.children = [self.header, self.scrolled_window]

        # Connect to audio service changes
        if audio_service:
            self._signal_connections.append(
                audio_service.connect("stream-added", self._on_stream_changed)
            )
            self._signal_connections.append(
                audio_service.connect("stream-removed", self._on_stream_changed)
            )

        # Track last known app names to avoid unnecessary rebuilds
        self._last_app_names = frozenset()

        # Initial population
        self._populate_apps()

        self.connect("map", self._on_map)
        self.connect("unmap", self._on_unmap)

    def _auto_refresh(self):
        """Auto-refresh the application list every 2 seconds"""
        if self._destroyed:
            self._refresh_timer = None
            return False
        if not audio_service:
            return True
        apps = audio_service.applications or []
        current_names = frozenset(a.name or "" for a in apps)
        if current_names != self._last_app_names:
            self._last_app_names = current_names
            self._populate_apps()
        return True

    def _on_map(self, *_):
        if self._refresh_timer is None:
            self._refresh_timer = GLib.timeout_add_seconds(2, self._auto_refresh)

    def _on_unmap(self, *_):
        if self._refresh_timer is not None:
            GLib.source_remove(self._refresh_timer)
            self._refresh_timer = None

    def _go_back(self, *_):
        """Return to main control center view"""
        self.control_center.close_per_app_volume()

    def _get_app_icon(self, app):
        """Get icon for application"""
        # Don't use fabric's generic audio icon, use description/name for better detection
        fabric_icon = getattr(app, "icon_name", "")
        if fabric_icon and fabric_icon != "audio":
            return fabric_icon

        # Use description first (more accurate), then name
        app_description = getattr(app, "description", "").lower()
        app_name = app.name.lower()

        # Check description first as it's more reliable
        search_text = app_description if app_description else app_name

        icon_mapping = _APP_ICON_MAPPING

        # Check if any key in mapping is contained in search text
        for key, icon in icon_mapping.items():
            if key in search_text:
                return icon

        # Also check app name as fallback
        if search_text != app_name:
            for key, icon in icon_mapping.items():
                if key in app_name:
                    return icon

        # Default audio icon for unknown apps
        return "audio-volume-high"

    def _format_app_name(self, name):
        """Format application name with proper capitalization"""
        if not name:
            return "Unknown"

        # Handle common app names specially
        name_lower = name.lower()
        if name_lower in _APP_SPECIAL_NAMES:
            return _APP_SPECIAL_NAMES[name_lower]

        # Default: capitalize first letter
        return name.capitalize()

    def _populate_apps(self):
        """Populate the widget with current audio applications"""
        # Clear and DESTROY existing widgets to prevent memory leaks
        for child in list(self.apps_container.get_children()):
            try:
                child.destroy()
            except Exception as e:
                logger.error(f"An error occurred: {e}")
        self.apps_container.children = []
        self._app_widgets.clear()

        # Use fabric audio service for applications
        if not audio_service:
            self._show_no_apps_message()
            return

        applications = getattr(audio_service, "applications", [])

        if applications:
            for i, app in enumerate(applications):
                if hasattr(app, "name") and hasattr(app, "volume"):
                    app_widget = self._create_app_control(app)
                    self.apps_container.children = [
                        *list(self.apps_container.children),
                        app_widget,
                    ]

                    # Add separator between apps (except for last one)
                    if i < len(applications) - 1:
                        separator = Separator(
                            orientation="horizontal",
                            style_classes="app-volume-separator",
                        )
                        self.apps_container.children = [
                            *list(self.apps_container.children),
                            separator,
                        ]

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
        """Create compact volume control for a single application"""
        # Format app name (shorter for compact layout)
        app_name = self._format_app_name(app.name)
        # Get current volume from fabric audio service
        current_volume = getattr(app, "volume", 0.0)
        max_vol = getattr(audio_service, "max_volume", 100) if audio_service else 100

        # Ensure volume is in valid range
        volume_percent = max(0, min(current_volume, max_vol))

        # App icon - use the same approach as expanded player
        icon_name = self._get_app_icon(app)
        app_icon = Image(
            icon_name=icon_name,
            name="app-icon",
            icon_size=16,
            style_classes="app-icon",
        )

        # App name label
        name_label = Label(
            label=app_name,
            style_classes="app-name-compact",
            justification="left",
            h_align="start",
            max_chars_width=10,
            ellipsization="end",
        )

        # Volume scale (smaller and horizontal)
        volume_scale = FlatScale(
            value=volume_percent,
            min_value=0,
            max_value=max_vol,
            step=5,
            name="compact-volume-slider",
            size=20,
            h_expand=True,
        )

        # Connect volume change handler
        volume_scale.connect(
            "value-changed",
            lambda scale, value, app=app: self._set_app_volume(app, value),
        )

        # Create horizontal compact layout
        app_control = Box(
            orientation="horizontal",
            spacing=5,
            h_expand=True,
            style_classes="compact-app-volume-item",
            children=[
                Box(
                    orientation="h",
                    spacing=3,
                    v_expand=True,
                    v_align="center",
                    name="app-control-box",
                    children=[
                        app_icon,
                        name_label,
                    ],
                ),
                volume_scale,
            ],
        )
        # Add separator after the control

        return app_control

    def _set_app_volume(self, app, volume_value):
        """Set volume for a specific application using fabric audio service"""
        if app.name in self._updating_volumes:
            return

        self._updating_volumes.add(app.name)

        try:
            # Get max volume from audio service
            max_vol = (
                getattr(audio_service, "max_volume", 100) if audio_service else 100
            )

            # Ensure volume is within bounds
            volume_value = max(0, min(volume_value, max_vol))

            # Set volume directly - fabric expects the actual volume value, not percentage
            app.volume = volume_value

        except Exception as e:
            logger.error(f"Error setting volume for {app.name}: {e}")
        finally:
            GLib.timeout_add(100, lambda: self._updating_volumes.discard(app.name))

    def _on_stream_changed(self, *_):
        """Handle when audio streams are added or removed"""
        if not self._destroyed:
            GLib.idle_add(self._populate_apps)

    def refresh(self):
        """Manually refresh the application list"""
        self._populate_apps()

    def destroy(self):
        """Clean up resources"""
        self._destroyed = True

        # Stop the auto-refresh timer
        if self._refresh_timer is not None:
            try:
                GLib.source_remove(self._refresh_timer)
            except Exception as e:
                logger.error(f"An error occurred: {e}")
            self._refresh_timer = None

        # Disconnect audio service signals
        if audio_service:
            for connection in self._signal_connections:
                try:
                    audio_service.disconnect(connection)
                except Exception as e:
                    logger.error(f"An error occurred: {e}")

        self._signal_connections.clear()
        self._app_widgets.clear()
        self._updating_volumes.clear()
        self.control_center = None

        super().destroy()
