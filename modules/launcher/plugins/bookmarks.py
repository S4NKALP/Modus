import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

from thefuzz import fuzz
from fabric.utils.helpers import get_relative_path

import utils.icons as icons
from modules.launcher.plugin_base import PluginBase
from modules.launcher.result import Result


class BookmarkManager:
    """Manages user's custom bookmarks."""

    def __init__(self, storage_file: Path):
        self.storage_file = storage_file
        self.bookmarks: List[Dict] = []
        self.cache_lock = threading.Lock()
        self.last_loaded = 0
        self.cache_ttl = 30  # Cache for 30 seconds
        self._load_bookmarks()

    def _get_favicon_url(self, url: str) -> str:
        """Generate favicon URL for a given website URL."""
        try:
            parsed = urlparse(url)
            return f"{parsed.scheme}://{parsed.netloc}/favicon.ico"
        except:
            return ""

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc
            # Remove www. prefix
            if domain.startswith("www."):
                domain = domain[4:]
            return domain
        except:
            return url

    def _normalize_url(self, url: str) -> str:
        """Normalize URL by adding protocol if missing."""
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            if url.startswith("www."):
                url = "https://" + url
            else:
                url = "https://" + url
        return url

    def _load_bookmarks(self):
        """Load bookmarks from JSON file with caching."""
        with self.cache_lock:
            current_time = time.time()

            # Check if cache is still valid
            if (current_time - self.last_loaded) < self.cache_ttl and self.bookmarks:
                return

            try:
                if self.storage_file.exists():
                    with open(self.storage_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self.bookmarks = data.get("bookmarks", [])
                else:
                    self.bookmarks = []

                self.last_loaded = current_time
            except Exception as e:
                print(f"Error loading bookmarks: {e}")
                self.bookmarks = []

    def get_bookmarks(self) -> List[Dict]:
        """Get bookmarks, loading from file if needed."""
        self._load_bookmarks()
        return self.bookmarks



    def _save_bookmarks_unlocked(self):
        """Save bookmarks to JSON file without acquiring lock."""
        try:
            self.storage_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "bookmarks": self.bookmarks,
                "last_updated": time.time(),
            }
            with open(self.storage_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            # Update cache timestamp
            self.last_loaded = time.time()
        except Exception as e:
            print(f"Error saving bookmarks: {e}")

    def _save_bookmarks(self):
        """Save bookmarks to JSON file."""
        with self.cache_lock:
            self._save_bookmarks_unlocked()

    def add_bookmark(self, title: str, url: str, description: str = "", tags: List[str] = None) -> bool:
        """Add a new bookmark."""
        try:
            url = self._normalize_url(url)

            # Check if bookmark already exists
            for bookmark in self.bookmarks:
                if bookmark["url"] == url:
                    return False  # Already exists

            new_bookmark = {
                "title": title.strip(),
                "url": url,
                "description": description.strip(),
                "tags": tags or [],
                "created": time.time(),
                "accessed": 0
            }

            self.bookmarks.append(new_bookmark)
            self._save_bookmarks()

            # Clear cache to force reload
            self.last_loaded = 0

            return True

        except Exception as e:
            print(f"Error adding bookmark: {e}")
            return False

    def remove_bookmark(self, identifier: str) -> bool:
        """Remove a bookmark by title or URL."""
        try:
            identifier = identifier.lower().strip()

            for i, bookmark in enumerate(self.bookmarks):
                if (bookmark["title"].lower() == identifier or
                    bookmark["url"].lower() == identifier or
                    self._extract_domain(bookmark["url"]).lower() == identifier):

                    self.bookmarks.pop(i)
                    self._save_bookmarks()

                    # Clear cache to force reload
                    self.last_loaded = 0

                    return True

            return False

        except Exception as e:
            print(f"Error removing bookmark: {e}")
            return False

    def update_access_time(self, url: str):
        """Update the last accessed time for a bookmark."""
        try:
            for bookmark in self.bookmarks:
                if bookmark["url"] == url:
                    bookmark["accessed"] = time.time()
                    self._save_bookmarks()
                    break
        except Exception as e:
            print(f"Error updating access time: {e}")

    def get_bookmark_count(self) -> int:
        """Get total number of bookmarks."""
        return len(self.get_bookmarks())


class BookmarksPlugin(PluginBase):
    """
    User bookmarks plugin for the launcher.
    Allows users to add, remove, and search their own bookmarks.
    """

    def __init__(self):
        super().__init__()
        self.display_name = "Bookmarks"
        self.description = "Manage and search your personal bookmarks"

        # Initialize bookmark manager with storage file
        self.bookmark_file = Path(get_relative_path("../../../config/json/bookmarks.json"))
        self.bookmark_manager = BookmarkManager(self.bookmark_file)
        self.max_results = 15

    def initialize(self):
        """Initialize the bookmarks plugin."""
        self.set_triggers(["bookmark", "bm"])

    def cleanup(self):
        """Cleanup the bookmarks plugin."""
        pass

    def query(self, query_string: str) -> List[Result]:
        """Process bookmark queries with add/remove commands."""
        query = query_string.strip()

        if not query:
            # Show recent/popular bookmarks when no query
            return self._get_recent_bookmarks()

        # Handle add command
        if query.startswith("add "):
            return self._handle_add_command(query[4:].strip())

        # Handle remove command
        if query.startswith(("remove ", "delete ", "rm ")):
            command_parts = query.split(" ", 1)
            if len(command_parts) > 1:
                return self._handle_remove_command(command_parts[1].strip())
            else:
                return self._show_remove_help()

        # Search bookmarks
        return self._search_bookmarks(query.lower())

    def _search_bookmarks(self, query: str) -> List[Result]:
        """Search through bookmarks."""
        bookmarks = self.bookmark_manager.get_bookmarks()

        if not bookmarks:
            return [
                Result(
                    title="No Bookmarks Found",
                    subtitle="Use 'add <title> <url>' to add your first bookmark",
                    icon_markup=icons.info,
                    action=lambda: None,
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={"type": "info", "keep_launcher_open": True}
                )
            ]

        # Search bookmarks
        results = []
        for bookmark in bookmarks:
            relevance = self._calculate_relevance(bookmark, query)
            if relevance > 0.3:  # Only show relevant results
                result = self._create_bookmark_result(bookmark, relevance)
                if result:
                    results.append(result)

        # Sort by relevance and limit results
        results.sort(key=lambda r: r.relevance, reverse=True)
        return results[:self.max_results]

    def _get_recent_bookmarks(self) -> List[Result]:
        """Get recent/popular bookmarks when no query is provided."""
        bookmarks = self.bookmark_manager.get_bookmarks()

        if not bookmarks:
            return [
                Result(
                    title="No Bookmarks Yet",
                    subtitle="Use 'add <title> <url>' to add your first bookmark",
                    icon_markup=icons.info,
                    action=lambda: None,
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={"type": "help", "keep_launcher_open": True}
                ),
                Result(
                    title="Example: Add Google",
                    subtitle="add Google https://google.com",
                    icon_markup=icons.bulb,
                    action=lambda: None,
                    relevance=0.9,
                    plugin_name=self.display_name,
                    data={"type": "example", "keep_launcher_open": True}
                )
            ]

        # Sort by access time (most recent first) and show top 10
        sorted_bookmarks = sorted(bookmarks, key=lambda b: b.get("accessed", 0), reverse=True)
        results = []
        for bookmark in sorted_bookmarks[:10]:
            result = self._create_bookmark_result(bookmark, 0.8)
            if result:
                results.append(result)

        return results

    def _handle_add_command(self, args: str) -> List[Result]:
        """Handle add bookmark command."""
        if not args:
            return [
                Result(
                    title="Add Bookmark",
                    subtitle="Usage: add <title> <url> [description]",
                    icon_markup=icons.info,
                    action=lambda: None,
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={"type": "help", "keep_launcher_open": True}
                ),
                Result(
                    title="Example",
                    subtitle="add Google https://google.com Search engine",
                    icon_markup=icons.bulb,
                    action=lambda: None,
                    relevance=0.9,
                    plugin_name=self.display_name,
                    data={"type": "example", "keep_launcher_open": True}
                )
            ]

        # Parse arguments: title url [description]
        parts = args.split()
        if len(parts) < 2:
            return [
                Result(
                    title="Invalid Format",
                    subtitle="Usage: add <title> <url> [description]",
                    icon_markup=icons.alert,
                    action=lambda: None,
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={"type": "error", "keep_launcher_open": True}
                )
            ]

        title = parts[0]
        url = parts[1]
        description = " ".join(parts[2:]) if len(parts) > 2 else ""

        # Add the bookmark
        success = self.bookmark_manager.add_bookmark(title, url, description)

        if success:
            return [
                Result(
                    title=f"✓ Added '{title}'",
                    subtitle=f"Bookmark saved: {url}",
                    icon_markup=icons.check,
                    action=lambda: None,
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={"type": "success"}
                )
            ]
        else:
            return [
                Result(
                    title="Bookmark Already Exists",
                    subtitle=f"A bookmark with URL '{url}' already exists",
                    icon_markup=icons.alert,
                    action=lambda: None,
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={"type": "error", "keep_launcher_open": True}
                )
            ]

    def _handle_remove_command(self, identifier: str) -> List[Result]:
        """Handle remove bookmark command."""
        if not identifier:
            return self._show_remove_help()

        success = self.bookmark_manager.remove_bookmark(identifier)

        if success:
            return [
                Result(
                    title=f"✓ Removed Bookmark",
                    subtitle=f"Bookmark '{identifier}' has been removed",
                    icon_markup=icons.check,
                    action=lambda: None,
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={"type": "success"}
                )
            ]
        else:
            return [
                Result(
                    title="Bookmark Not Found",
                    subtitle=f"No bookmark found matching '{identifier}'",
                    icon_markup=icons.alert,
                    action=lambda: None,
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={"type": "error", "keep_launcher_open": True}
                )
            ]

    def _show_remove_help(self) -> List[Result]:
        """Show help for remove command."""
        bookmarks = self.bookmark_manager.get_bookmarks()
        results = [
            Result(
                title="Remove Bookmark",
                subtitle="Usage: remove <title|url|domain>",
                icon_markup=icons.info,
                action=lambda: None,
                relevance=1.0,
                plugin_name=self.display_name,
                data={"type": "help", "keep_launcher_open": True}
            )
        ]

        # Show available bookmarks to remove
        if bookmarks:
            results.append(
                Result(
                    title="Available Bookmarks:",
                    subtitle=f"{len(bookmarks)} bookmarks available to remove",
                    icon_markup=icons.bookmark,
                    action=lambda: None,
                    relevance=0.9,
                    plugin_name=self.display_name,
                    data={"type": "info", "keep_launcher_open": True}
                )
            )

            # Show first few bookmarks as examples
            for bookmark in bookmarks[:3]:
                title = bookmark.get("title", "Untitled")
                domain = self._extract_domain(bookmark.get("url", ""))
                results.append(
                    Result(
                        title=f"remove {title}",
                        subtitle=f"Remove: {title} ({domain})",
                        icon_markup=icons.trash,
                        action=lambda t=title: self.bookmark_manager.remove_bookmark(t),
                        relevance=0.8,
                        plugin_name=self.display_name,
                        data={"type": "remove_option", "bookmark": bookmark}
                    )
                )

        return results

    def _calculate_relevance(self, bookmark: Dict, query: str) -> float:
        """Calculate relevance score for a bookmark."""
        title = bookmark.get("title", "").lower()
        url = bookmark.get("url", "").lower()
        description = bookmark.get("description", "").lower()

        # Exact title match
        if query == title:
            return 1.0

        # Title starts with query
        if title.startswith(query):
            return 0.95

        # Query in title
        if query in title:
            position = title.index(query)
            position_score = 1.0 - (position / len(title))
            return 0.8 + (position_score * 0.1)

        # Query in URL
        if query in url:
            return 0.7

        # Query in description
        if query in description:
            return 0.6

        # Fuzzy matching for title
        if len(query) >= 3:
            fuzzy_score = fuzz.partial_ratio(query, title) / 100.0
            if fuzzy_score >= 0.7:
                return fuzzy_score * 0.6

        return 0.0

    def _create_bookmark_result(self, bookmark: Dict, relevance: float) -> Optional[Result]:
        """Create a Result object for a bookmark."""
        try:
            title = bookmark.get("title", "Untitled")
            url = bookmark.get("url", "")
            description = bookmark.get("description", "")

            # Truncate long titles
            if len(title) > 60:
                title = title[:57] + "..."

            # Create subtitle with domain and description
            domain = self._extract_domain(url)
            if description:
                subtitle = f"{domain} • {description}"
            else:
                subtitle = domain

            return Result(
                title=title,
                subtitle=subtitle,
                icon_markup=icons.bookmark,
                action=lambda u=url: self._open_bookmark(u),
                relevance=relevance,
                plugin_name=self.display_name,
                data={
                    "type": "bookmark",
                    "url": url,
                    "domain": domain,
                    "description": description
                }
            )
        except Exception as e:
            print(f"Error creating bookmark result: {e}")
            return None

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc
            # Remove www. prefix
            if domain.startswith("www."):
                domain = domain[4:]
            return domain
        except:
            return url

    def _open_bookmark(self, url: str):
        """Open bookmark URL in default browser and update access time."""
        try:
            # Update access time
            self.bookmark_manager.update_access_time(url)

            # Open URL
            subprocess.Popen(
                ["xdg-open", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception as e:
            print(f"Failed to open bookmark: {e}")
