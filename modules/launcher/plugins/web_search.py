from typing import List, Dict, Any
from fabric.utils import exec_shell_command_async
from . import LauncherPlugin


class WebSearchPlugin(LauncherPlugin):
    """Plugin for web search functionality"""

    @property
    def name(self) -> str:
        return "Web Search"

    @property
    def category(self) -> str:
        return "Web"

    @property
    def icon_name(self) -> str:
        return "web-browser-symbolic"

    def search(self, query: str) -> List[Dict[str, Any]]:
        if not query:
            return []

        return [
            {
                "title": f'Search the web for "{query}"',
                "description": "Open in default browser",
                "icon_name": "web-browser-symbolic",
                "action": lambda q=query: self.search_web(q),
            }
        ]

    def get_action_items(self, query: str) -> List[Dict[str, Any]]:
        if not query:
            return []

        return [
            {
                "title": f'Search web for "{query}"',
                "icon_name": "web-browser-symbolic",
                "action": lambda q=query: self.search_web(q),
            }
        ]

    def search_web(self, query: str):
        # Use xdg-open to open the default browser with a search query
        search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
        exec_shell_command_async(f"xdg-open '{search_url}'", lambda *_: None)
