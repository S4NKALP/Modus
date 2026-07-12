from abc import ABC, abstractmethod
from typing import Any

from window.spotlight.api.context import PluginContext
from window.spotlight.api.result import SearchResult


class SpotlightPlugin(ABC):
    """Base class for all spotlight plugins.

    Plugins provide data via search(). Never create GTK widgets.

    Attributes:
        id: Unique identifier (e.g., "calculator").
        name: Human-readable name (e.g., "Calculator").
        icon: Default GTK icon name.
        keywords: Trigger words that route queries exclusively.
        searchable: Whether plugin participates in global search.
        priority: Lower = searched first.
        refresh_interval: Auto-refresh interval in ms (0 = disabled).
    """

    id: str = ""
    name: str = ""
    icon: str = ""
    keywords: list[str] | None = None
    keyword_icons: dict[str, str] | None = None
    searchable: bool = False
    priority: int = 100
    refresh_interval: int = 0

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.keywords is None:
            cls.keywords = []
        if cls.keyword_icons is None:
            cls.keyword_icons = {}

    def __init__(self, context: PluginContext):
        self.context = context

    def initialize(self) -> None:
        """Called once after instantiation. Override for setup."""

    def cleanup(self) -> None:
        """Called on unload/disable. Override to release resources."""

    def reload(self) -> None:
        """Called when plugin needs to refresh its state.
        Default: cleanup + re-initialize."""
        self.cleanup()
        self.initialize()

    @abstractmethod
    def search(self, query: str, token: Any) -> list[SearchResult]:
        """Return results matching query.

        token: Cancellation token. Check token.is_cancelled before expensive work.
        Must return list of SearchResult. Never create GTK widgets.
        """
        ...

    def on_activate(self, update_fn=None) -> None:
        """Called when keyword routes to this plugin.

        update_fn: callable(result_id, subtitle_text) for in-place label updates.
        """

    def on_deactivate(self) -> None:
        """Called when keyword routes away from this plugin."""

    def on_submit(self, query: str) -> None:
        """Called when user presses Enter while this plugin is active."""

    def detect(self, text: str) -> bool:
        """Return True if this plugin should exclusively handle the input."""
        return False

    def handle_external(self, command: str, args: str) -> None:
        """Handle external commands sent to the plugin."""

    def release_memory(self) -> None:
        """Release heavy cached data. Called when spotlight hides.

        Plugins should clear large caches here. They will be
        reloaded lazily on next search.
        """

    def on_timer_tick(self) -> list[SearchResult] | None:
        """Called every second when the plugin is active.

        Return updated results to re-render, or None to skip.
        Used for live data like countdown timers.
        """
