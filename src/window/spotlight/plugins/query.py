import urllib.parse
from typing import Any

from utils.functions import spawn_detached
from window.spotlight.api import PluginContext, SearchResult, SpotlightPlugin


class QueryPlugin(SpotlightPlugin):
    id = "query"
    name = "Query"
    icon = "system-search-symbolic"
    keywords = ["gg", "yt", "lk"]
    keyword_icons = {
        "gg": "edit-find-symbolic",
        "yt": "video-x-generic-symbolic",
        "lk": "insert-link-symbolic",
    }
    searchable = False
    priority = 100

    def __init__(self, context: PluginContext):
        super().__init__(context)

    def initialize(self) -> None:
        pass

    def cleanup(self) -> None:
        pass

    def release_memory(self) -> None:
        pass

    def search(self, query: str, token: Any) -> list[SearchResult]:
        q = query.strip()
        if not q:
            return []

        bare = q.lower()
        if bare in ("gg", "yt", "lk"):
            hints = {
                "gg": ("Google Search", "Type 'gg <query>' to search"),
                "yt": ("YouTube Search", "Type 'yt <query>' to search"),
                "lk": ("Open Link", "Type 'lk <url>' to open"),
            }
            title, subtitle = hints[bare]
            return [
                SearchResult(
                    id=f"query_{bare}_hint",
                    title=title,
                    subtitle=subtitle,
                    icon_name=self.keyword_icons.get(bare, self.icon),
                    score=100.0,
                    render_type="default",
                )
            ]

        if q.lower().startswith("gg "):
            search_q = q[3:].strip()
            if not search_q:
                return []
            return [
                SearchResult(
                    id="query_gg",
                    title=f"Google: {search_q}",
                    subtitle="Open in browser",
                    icon_name="system-search-symbolic",
                    score=100.0,
                    render_type="default",
                    action=lambda: self._google_search(search_q),
                )
            ]
        if q.lower().startswith("yt "):
            search_q = q[3:].strip()
            if not search_q:
                return []
            return [
                SearchResult(
                    id="query_yt",
                    title=f"YouTube: {search_q}",
                    subtitle="Open in browser",
                    icon_name="system-search-symbolic",
                    score=100.0,
                    render_type="default",
                    action=lambda: self._youtube_search(search_q),
                )
            ]
        if q.lower().startswith("lk "):
            link = q[3:].strip()
            if not link:
                return []
            if not link.startswith("http"):
                link = "https://" + link
            return [
                SearchResult(
                    id="query_lk",
                    title=f"Open: {link}",
                    subtitle="Open in browser",
                    icon_name="system-search-symbolic",
                    score=100.0,
                    render_type="default",
                    action=lambda: self._link_open(link),
                )
            ]
        return []

    def on_submit(self, query: str) -> None:
        q = query.strip()
        if q.startswith("gg "):
            self._google_search(q[3:].strip())
        elif q.startswith("yt "):
            self._youtube_search(q[3:].strip())
        elif q.startswith("lk "):
            self._link_open(q.split(" ", 1)[1].strip())

    def _google_search(self, query: str) -> None:
        url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
        spawn_detached(["xdg-open", url])

    def _youtube_search(self, query: str) -> None:
        url = (
            f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
        )
        spawn_detached(["xdg-open", url])

    def _link_open(self, link: str) -> None:
        if not link.startswith(("http://", "https://")):
            link = "https://" + link
        spawn_detached(["xdg-open", link])

    def handle_external(self, command: str, args: str) -> None:
        pass


PLUGIN = QueryPlugin
