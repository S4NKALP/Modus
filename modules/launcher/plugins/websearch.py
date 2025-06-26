import subprocess
import urllib.parse
from typing import List

import utils.icons as icons
from modules.launcher.plugin_base import PluginBase
from modules.launcher.result import Result


class WebSearchPlugin(PluginBase):
    """
    Web search plugin that supports multiple search engines.
    """

    def __init__(self):
        super().__init__()
        self.display_name = "Web Search"
        self.description = "Search the web using various search engines"
        self.current_trigger = ""  # Track the current active trigger

        # Define search engines with their URLs and icons
        self.search_engines = {
            "google": {
                "name": "Google",
                "url": "https://www.google.com/search?q={}",
                "icon": icons.google,
                "description": "Search with Google",
            },
            "duckduckgo": {
                "name": "DuckDuckGo",
                "url": "https://duckduckgo.com/?q={}",
                "icon": icons.duckduckgo,
                "description": "Search with DuckDuckGo (privacy-focused)",
            },
            "youtube": {
                "name": "YouTube",
                "url": "https://www.youtube.com/results?search_query={}",
                "icon": icons.youtube,
                "description": "Search videos on YouTube",
            },
            "github": {
                "name": "GitHub",
                "url": "https://github.com/search?q={}",
                "icon": icons.github,
                "description": "Search repositories on GitHub",
            },
            "stackoverflow": {
                "name": "Stack Overflow",
                "url": "https://stackoverflow.com/search?q={}",
                "icon": icons.stackoverflow,
                "description": "Search programming questions on Stack Overflow",
            },
            "wikipedia": {
                "name": "Wikipedia",
                "url": "https://en.wikipedia.org/wiki/Special:Search?search={}",
                "icon": icons.wikipedia,
                "description": "Search articles on Wikipedia",
            },
            "reddit": {
                "name": "Reddit",
                "url": "https://www.reddit.com/search/?q={}",
                "icon": icons.reddit,
                "description": "Search discussions on Reddit",
            },
            "linkedin": {
                "name": "LinkedIn",
                "url": "https://www.linkedin.com/search/results/all/?keywords={}",
                "icon": icons.linkedin,
                "description": "Search professionals and jobs on LinkedIn",
            },
        }

        # Default search engine
        self.default_engine = "google"

    def initialize(self):
        """Initialize the web search plugin."""
        # Set up triggers for web search - only main triggers, not individual search engines
        triggers = ["?"]

        # Don't add individual search engine triggers to avoid cluttering trigger keywords
        # Search engines can still be used within web search context (e.g., "web google cats")

        self.set_triggers(triggers)

    def get_active_trigger(self, query_string: str) -> str:
        """Override to track which trigger was activated."""
        trigger = super().get_active_trigger(query_string)
        if trigger:
            self.current_trigger = trigger.strip()
        return trigger

    def cleanup(self):
        """Cleanup the web search plugin."""
        pass

    def query(self, query_string: str) -> List[Result]:
        """Process web search queries."""
        results = []

        if not query_string.strip():
            # Show available search engines when no query
            return self._get_search_engine_list()

        # Check if the query is a URL
        if self._is_url(query_string):
            results.append(self._create_url_result(query_string))
            return results

        # Parse query to check if it starts with a search engine name
        engine_name, search_query = self._parse_engine_query(query_string)

        if engine_name and engine_name in self.search_engines:
            # Specific search engine specified in query (e.g., "google cats")
            if search_query:
                # Search with specific engine
                results.append(self._create_search_result(engine_name, search_query))
            else:
                # Show specific engine info
                results.append(self._create_engine_info_result(engine_name))
        else:
            # General search - offer multiple engines
            search_query = query_string.strip()

            # Add default search engine first
            results.append(
                self._create_search_result(self.default_engine, search_query)
            )

            # Add other popular search engines
            popular_engines = ["duckduckgo", "youtube", "github"]
            for engine in popular_engines:
                if engine != self.default_engine:
                    results.append(self._create_search_result(engine, search_query))

        return results

    def _parse_engine_query(self, query: str) -> tuple[str, str]:
        """Parse query to extract search engine and search terms."""
        query = query.strip().lower()

        for engine in self.search_engines.keys():
            if query.startswith(f"{engine} "):
                return engine, query[len(engine) :].strip()
            elif query == engine:
                return engine, ""

        return "", query

    def _is_url(self, text: str) -> bool:
        """Check if the text is a URL."""
        text = text.strip().lower()
        return text.startswith(("http://", "https://", "www.")) or (
            "." in text and " " not in text and len(text) > 3
        )

    def _create_url_result(self, url: str) -> Result:
        """Create a result for opening a URL directly."""
        # Add protocol if missing
        if not url.startswith(("http://", "https://")):
            if url.startswith("www."):
                url = "https://" + url
            else:
                url = "https://" + url

        return Result(
            title=f"Open {url}",
            subtitle="Open this URL in your default browser",
            icon_markup=icons.world,
            action=lambda u=url: self._open_url(u),
            relevance=1.0,
            plugin_name=self.display_name,
            data={"type": "url", "url": url},
        )

    def _open_url(self, url: str):
        """Open a URL directly in the default browser."""
        try:
            subprocess.Popen(
                ["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except Exception as e:
            print(f"Failed to open URL: {e}")

    def _get_search_engine_list(self) -> List[Result]:
        """Get list of available search engines."""
        results = []

        for engine_id, engine_info in self.search_engines.items():
            result = Result(
                title=engine_info["name"],
                subtitle=engine_info["description"],
                icon_markup=engine_info["icon"],
                action=lambda e=engine_id: self._show_engine_help(e),
                relevance=1.0 if engine_id == self.default_engine else 0.8,
                plugin_name=self.display_name,
                data={"type": "engine_info", "engine": engine_id},
            )
            results.append(result)

        return results

    def _create_search_result(self, engine_id: str, query: str) -> Result:
        """Create a search result for a specific engine and query."""
        engine_info = self.search_engines[engine_id]

        return Result(
            title=f"Search '{query}' on {engine_info['name']}",
            subtitle=f"{engine_info['description']} - {query}",
            icon_markup=engine_info["icon"],
            action=lambda e=engine_id, q=query: self._perform_search(e, q),
            relevance=1.0 if engine_id == self.default_engine else 0.9,
            plugin_name=self.display_name,
            data={"type": "search", "engine": engine_id, "query": query},
        )

    def _create_engine_info_result(self, engine_id: str) -> Result:
        """Create an info result for a specific search engine."""
        engine_info = self.search_engines[engine_id]

        return Result(
            title=f"{engine_info['name']} Search",
            subtitle=f"{engine_info['description']} - Type your search query",
            icon_markup=engine_info["icon"],
            action=lambda: None,  # No action for info result
            relevance=1.0,
            plugin_name=self.display_name,
            data={"type": "engine_ready", "engine": engine_id},
        )

    def _perform_search(self, engine_id: str, query: str):
        """Perform a web search using the specified engine."""
        if not query.strip():
            return

        engine_info = self.search_engines.get(engine_id)
        if not engine_info:
            return

        # URL encode the search query
        encoded_query = urllib.parse.quote_plus(query)
        search_url = engine_info["url"].format(encoded_query)

        try:
            # Open the search URL in the default browser
            subprocess.Popen(
                ["xdg-open", search_url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            print(f"Failed to open search URL: {e}")

    def _show_engine_help(self, engine_id: str):
        """Show help for a specific search engine."""
        engine_info = self.search_engines.get(engine_id)
        if engine_info:
            print(
                f"Search engine: {engine_info['name']} - {engine_info['description']}"
            )
