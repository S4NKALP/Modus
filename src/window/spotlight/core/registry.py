from dataclasses import dataclass, field
from typing import Type

from fabric.utils import logger

from window.spotlight.api.plugin import SpotlightPlugin
from window.spotlight.core.loader import DiscoveredPlugin


@dataclass
class PluginEntry:
    """Internal bookkeeping for a registered plugin."""

    id: str
    plugin_class: Type[SpotlightPlugin]
    source: str
    path: str
    instance: SpotlightPlugin | None = None
    enabled: bool = True
    keywords: list[str] = field(default_factory=list)
    module_name: str = ""


class PluginRegistry:
    """Stores loaded plugin metadata and instances.

    Responsibilities:
      - Register/unregister plugins
      - Lookup by id, keyword
      - Prevent duplicates
      - Track enabled/disabled state
    """

    def __init__(self):
        self._entries: dict[str, PluginEntry] = {}
        self._keyword_map: dict[str, str] = {}  # keyword -> plugin_id

    def register(self, discovered: DiscoveredPlugin) -> bool:
        """Register a discovered plugin. Returns False if duplicate id."""
        cls = discovered.plugin_class
        pid = cls.id
        if not pid:
            logger.warning(
                f"[PluginRegistry] Plugin {cls.__name__} has no id, skipping"
            )
            return False

        if pid in self._entries:
            logger.warning(
                f"[PluginRegistry] Duplicate plugin id '{pid}' from "
                f"{discovered.path}, ignoring"
            )
            return False

        entry = PluginEntry(
            id=pid,
            plugin_class=cls,
            source=discovered.source,
            path=discovered.path,
            keywords=list(cls.keywords) if cls.keywords else [],
            module_name=discovered.module_name,
        )
        self._entries[pid] = entry

        for kw in entry.keywords:
            if kw in self._keyword_map:
                logger.warning(
                    f"[PluginRegistry] Keyword '{kw}' already mapped to "
                    f"'{self._keyword_map[kw]}', overriding with '{pid}'"
                )
            self._keyword_map[kw] = pid

        return True

    def unregister(self, plugin_id: str) -> bool:
        entry = self._entries.pop(plugin_id, None)
        if not entry:
            return False
        for kw in entry.keywords:
            if self._keyword_map.get(kw) == plugin_id:
                del self._keyword_map[kw]
        return True

    def get(self, plugin_id: str) -> PluginEntry | None:
        return self._entries.get(plugin_id)

    def get_all(self) -> list[PluginEntry]:
        return list(self._entries.values())

    def get_enabled(self) -> list[PluginEntry]:
        return [e for e in self._entries.values() if e.enabled]

    def get_searchable(self) -> list[PluginEntry]:
        return [
            e for e in self._entries.values() if e.enabled and e.plugin_class.searchable
        ]

    def get_by_keyword(self, keyword: str) -> PluginEntry | None:
        pid = self._keyword_map.get(keyword)
        if pid:
            return self._entries.get(pid)
        return None

    def is_registered(self, plugin_id: str) -> bool:
        return plugin_id in self._entries

    def set_enabled(self, plugin_id: str, enabled: bool) -> bool:
        entry = self._entries.get(plugin_id)
        if not entry:
            return False
        entry.enabled = enabled
        return True
