import urllib.parse

from fabric.utils import exec_shell_command_async

from modules.launcher.base import LauncherPlugin


class QueryPlugin(LauncherPlugin):
    @property
    def name(self) -> str:
        return "query"

    @property
    def icon(self) -> str:
        # Dynamic icon based on active keyword would be better, but for now return a default
        # The main launcher handles icon updates for now based on keyword match
        return "system-search-symbolic"

    @property
    def keywords(self) -> list[str]:
        return ["gg", "yt", "lk"]

    @property
    def full_viewport_clear(self) -> bool:
        return True

    def stop(self):
        # No cleanup needed for query plugin
        pass

    def on_search(self, text: str) -> None:
        # The actual execution happens on Enter (on_entry_accept in main.py)
        # But we can also implement live search results here if we wanted to.
        # For now, we just acknowledge the search to keep the UI responsive
        pass

    def query_google(self, text: str) -> None:
        pass

    def query_link(self, link: str) -> None:
        pass

    def query_youtube(self, text: str) -> None:
        pass

    def on_submit(self, text: str) -> None:
        if text.startswith("gg "):
            self.handle_google_search(text[2:].strip())
        elif text.startswith("yt "):
            self.handle_youtube_search(text[3:].strip())
        elif text.startswith("lk "):
            self.handle_link_open(text.split(" ", 1)[1].strip())

    def handle_google_search(self, query: str) -> None:
        """Handle Google search - opens browser immediately"""
        self.handler.launched()
        return exec_shell_command_async(  # pyright: ignore[reportReturnType]
            f"xdg-open https://www.google.com/search?q={urllib.parse.quote(query)}"
        )

    def handle_link_open(self, link: str) -> None:
        """Handle link opening - opens browser immediately"""
        self.handler.launched()
        return exec_shell_command_async(  # pyright: ignore[reportReturnType]
            f"xdg-open {('https://' + link) if not link.startswith('http') else link}"
        )

    def handle_youtube_search(self, query: str) -> None:
        """Handle YouTube search - opens browser immediately"""
        self.handler.launched()
        return exec_shell_command_async(  # pyright: ignore[reportReturnType]
            f"xdg-open https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
        )
