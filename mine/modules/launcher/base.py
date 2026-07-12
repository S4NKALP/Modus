from abc import ABC, abstractmethod
from typing import Any


class LauncherPlugin(ABC):
    """Base class for all launcher plugins."""

    def __init__(self, handler: Any):
        self.handler = handler

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name of the plugin."""
        pass

    @property
    @abstractmethod
    def icon(self) -> str:
        """Icon name for the plugin."""
        pass

    @property
    @abstractmethod
    def keywords(self) -> list[str]:
        """List of keywords that trigger this plugin."""
        pass

    @property
    def full_viewport_clear(self) -> bool:
        """Whether the plugin needs to clear the viewport and hide the scroll window when activated."""
        return False

    @property
    def is_password_mode(self) -> bool:
        """Whether the plugin is currently in password mode (input should be masked)."""
        return False

    @abstractmethod
    def on_search(self, text: str) -> None:
        """Called when the user types in the launcher while this plugin is active."""
        pass

    def on_activate(self) -> None:
        """Called when the plugin is activated (e.g. by keyword)."""
        pass

    def on_deactivate(self) -> None:
        """Called when the plugin is deactivated."""
        pass

    def handle_external(self, command: str, args: str) -> None:
        """Handle external commands sent to the plugin."""
        pass

    def on_submit(self, text: str) -> None:
        """Called when the user presses Enter while this plugin is active."""
        pass
