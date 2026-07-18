from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class SearchResult:
    """Data carrier for a single search result.

    Plugins return these. Never create GTK widgets.
    The spotlight owns all rendering.
    """

    id: str
    title: str
    subtitle: str = ""
    icon_name: str = ""
    icon_data: bytes | None = None
    score: float = 0.0
    action: Callable[[], Any] | None = None
    render_type: str = "default"
    plugin_name: str = ""
    plugin_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.score = max(0.0, min(100.0, self.score))

    def activate(self):
        if self.action:
            return self.action()
        return None
