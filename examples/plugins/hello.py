"""Example: simplest possible single-file plugin.

Usage:
  cp examples/plugins/hello.py config/plugins/hello.py

  Then open spotlight and type "hi" or "hello".
  Or deep-reload from terminal:
    fabric-cli exec modus1 'deep_reload hello'
"""

from typing import Any

from window.spotlight.api import SearchResult, SpotlightPlugin


class HelloPlugin(SpotlightPlugin):
    id = "hello"
    name = "Hello"
    icon = "face-smile-symbolic"
    keywords = ["hi", "hello"]
    searchable = True
    priority = 100

    def initialize(self) -> None:
        pass

    def cleanup(self) -> None:
        pass

    def search(self, query: str, token: Any) -> list[SearchResult]:
        if not query.strip():
            return []
        return [
            SearchResult(
                id="hello_world",
                title="Hello, World!",
                subtitle="A friendly greeting",
                icon_name="face-smile-symbolic",
                score=100.0,
                render_type="default",
                action=lambda: print("Hello!"),
            )
        ]


PLUGIN = HelloPlugin
