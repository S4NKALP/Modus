import threading
from dataclasses import dataclass, field
from typing import Callable

from fabric.utils import GLib, logger

from window.spotlight.api.plugin import SpotlightPlugin
from window.spotlight.api.result import SearchResult
from window.spotlight.core.manager import PluginManager
from window.spotlight.core.registry import PluginEntry


@dataclass
class SearchToken:
    """Cancellation token for search operations."""

    query: str
    _cancelled: threading.Event = field(default_factory=threading.Event, repr=False)

    def cancel(self) -> None:
        self._cancelled.set()

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()


class SearchPipeline:
    """Async search pipeline that routes queries and merges results."""

    def __init__(self, manager: PluginManager):
        self._manager = manager
        self._current_token: SearchToken | None = None
        self._pending_threads: list[threading.Thread] = []
        self._pending_idle_ids: list[int] = []
        self._lock = threading.Lock()

    def search(
        self,
        query: str,
        callback: Callable[[list[SearchResult]], None],
    ) -> None:
        self._cancel_current()

        if not query.strip():
            callback([])
            return

        token = SearchToken(query=query)
        self._current_token = token

        keyword_plugin, _kw, _remaining = self._route(query)

        if keyword_plugin:
            self._search_single(keyword_plugin, query, token, callback)
        else:
            self._global_search(query, token, callback)

    def search_single(
        self,
        entry: PluginEntry,
        query: str,
        callback: Callable[[list[SearchResult]], None],
    ) -> None:
        self._cancel_current()
        token = SearchToken(query=query)
        self._current_token = token
        self._search_single(entry, query, token, callback)

    def cancel(self) -> None:
        self._cancel_current()

    def _cancel_current(self) -> None:
        if self._current_token:
            self._current_token.cancel()
        with self._lock:
            for t in self._pending_threads:
                t.join(timeout=0.1)
            self._pending_threads.clear()
            for source_id in self._pending_idle_ids:
                GLib.source_remove(source_id)
            self._pending_idle_ids.clear()

    def _route(self, query: str) -> tuple[PluginEntry | None, str, str]:
        stripped = query.strip()
        lower = stripped.lower()
        registry = self._manager.registry

        for entry in registry.get_enabled():
            for keyword in entry.keywords:
                kw = keyword.lower()
                if lower.startswith(kw + " ") or lower == kw:
                    remaining = stripped[len(keyword) :].lstrip()
                    return entry, keyword, remaining

        return None, "", query

    def _search_single(
        self,
        entry: PluginEntry,
        query: str,
        token: SearchToken,
        callback: Callable[[list[SearchResult]], None],
    ) -> None:
        instance = entry.instance
        if not instance:
            callback([])
            return

        def _run():
            try:
                results = self._safe_search(instance, query, token)
                self._stamp_results(results, entry)
                if not token.is_cancelled:

                    def _fire():
                        with self._lock:
                            try:
                                self._pending_idle_ids.remove(source_id)
                            except ValueError:
                                pass
                        callback(results)
                        return False

                    source_id = GLib.idle_add(_fire)
                    with self._lock:
                        self._pending_idle_ids.append(source_id)
            except Exception as e:
                logger.error(f"[SearchPipeline] Error searching {entry.id}: {e}")
                if not token.is_cancelled:

                    def _fire_err():
                        with self._lock:
                            try:
                                self._pending_idle_ids.remove(source_id)
                            except ValueError:
                                pass
                        callback([])
                        return False

                    source_id = GLib.idle_add(_fire_err)
                    with self._lock:
                        self._pending_idle_ids.append(source_id)

        thread = threading.Thread(target=_run, daemon=True)
        with self._lock:
            self._pending_threads.append(thread)
        thread.start()

    def _global_search(
        self,
        query: str,
        token: SearchToken,
        callback: Callable[[list[SearchResult]], None],
    ) -> None:
        searchable = self._manager.registry.get_searchable()
        if not searchable:
            callback([])
            return

        results_lock = threading.Lock()
        collected: dict[str, list[SearchResult]] = {}
        remaining = len(searchable)

        def _on_all_done():
            if token.is_cancelled:
                return
            merged = self._merge_results(collected)
            callback(merged)

        def _plugin_done(plugin_id: str):
            nonlocal remaining
            with results_lock:
                remaining -= 1
                if remaining <= 0:

                    def _fire_all_done():
                        with self._lock:
                            try:
                                self._pending_idle_ids.remove(source_id)
                            except ValueError:
                                pass
                        _on_all_done()
                        return False

                    source_id = GLib.idle_add(_fire_all_done)
                    with self._lock:
                        self._pending_idle_ids.append(source_id)

        def _run(entry: PluginEntry):
            instance = entry.instance
            if not instance or token.is_cancelled:
                _plugin_done(entry.id)
                return

            try:
                results = self._safe_search(instance, query, token)
                self._stamp_results(results, entry)
                with results_lock:
                    collected[entry.id] = results
            except Exception as e:
                logger.error(f"[SearchPipeline] Plugin {entry.id} crashed: {e}")
            finally:
                _plugin_done(entry.id)

        for entry in searchable:
            thread = threading.Thread(target=_run, args=(entry,), daemon=True)
            with self._lock:
                self._pending_threads.append(thread)
            thread.start()

    def _safe_search(
        self,
        plugin: SpotlightPlugin,
        query: str,
        token: SearchToken,
    ) -> list[SearchResult]:
        if token.is_cancelled:
            return []
        results = plugin.search(query, token)
        if token.is_cancelled:
            return []
        return results or []

    def _stamp_results(self, results: list[SearchResult], entry: PluginEntry) -> None:
        for r in results:
            if not r.plugin_name:
                r.plugin_name = entry.plugin_class.name
            if not r.plugin_id:
                r.plugin_id = entry.id

    def _merge_results(
        self, grouped: dict[str, list[SearchResult]]
    ) -> list[SearchResult]:
        enabled = {e.id: e for e in self._manager.registry.get_enabled()}

        ordered_ids = sorted(
            grouped.keys(),
            key=lambda pid: (
                enabled[pid].plugin_class.priority if pid in enabled else 999
            ),
        )

        merged: list[SearchResult] = []
        for pid in ordered_ids:
            plugin_results = grouped[pid]
            plugin_results.sort(key=lambda r: r.score, reverse=True)
            merged.extend(plugin_results)

        return merged
