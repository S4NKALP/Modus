import json
import subprocess
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

from fabric.utils.helpers import get_relative_path
from thefuzz import fuzz

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
            if (
                current_time - self.last_loaded
            ) < self.cache_ttl and self.last_loaded > 0:
                return

            try:
                if self.storage_file.exists():
                    with open(self.storage_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self.bookmarks = data.get("bookmarks", [])
                else:
                    # File doesn't exist, start with empty list but don't save yet
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

    def add_bookmark(
        self, title: str, url: str, description: str = "", tags: List[str] = None
    ) -> bool:
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
                "accessed": 0,
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
                if (
                    bookmark["title"].lower() == identifier
                    or bookmark["url"].lower() == identifier
                    or self._extract_domain(bookmark["url"]).lower() == identifier
                ):
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
        self.bookmark_file = Path(
            get_relative_path("../../../config/assets/bookmarks.json")
        )
        self.bookmark_manager = BookmarkManager(self.bookmark_file)
        self.max_results = 15

        # Cache for results
        self._results_cache = {}
        self._cache_timestamps = {}
        self._cache_ttl = 30  # 30 seconds

        # Launcher instance for refreshing
        self._launcher_instance = None
        self._original_close_launcher = None

    def initialize(self):
        """Initialize the bookmarks plugin."""
        self.set_triggers(["bm"])
        self._setup_launcher_hooks()

    def cleanup(self):
        """Cleanup the bookmarks plugin."""
        self._results_cache.clear()
        self._cache_timestamps.clear()
        self._cleanup_launcher_hooks()

    def query(self, query_string: str) -> List[Result]:
        """Process bookmark queries with caching."""
        query_key = query_string.strip()
        current_time = time.time()

        # Check cache first (except for add/remove commands which should always execute)
        if (
            not query_key.startswith(("add ", "remove ", "delete ", "rm "))
            and query_key in self._results_cache
            and (current_time - self._cache_timestamps.get(query_key, 0))
            < self._cache_ttl
        ):
            return self._results_cache[query_key]

        query = query_key.lower()
        results = []

        if not query:
            # Show recent/popular bookmarks when no query
            results = self._get_recent_bookmarks()
        elif query.startswith("add "):
            # Add new bookmark (don't cache)
            results = self._handle_add_command(query[4:].strip())
        elif query.startswith(("remove ", "delete ", "rm ")):
            # Remove bookmark (don't cache)
            command_parts = query_key.split(" ", 1)
            if len(command_parts) > 1:
                results = self._handle_remove_command(command_parts[1].strip())
            else:
                results = self._show_remove_help()
        else:
            # Search bookmarks
            results = self._search_bookmarks(query)

        # Cache results (except for add/remove commands)
        if not query.startswith(("add ", "remove ", "delete ", "rm ")):
            self._results_cache[query_key] = results
            self._cache_timestamps[query_key] = current_time

        return results

    def _search_bookmarks(self, query: str) -> List[Result]:
        """Search through bookmarks."""
        bookmarks = self.bookmark_manager.get_bookmarks()

        if not bookmarks:
            return [
                Result(
                    title="No Bookmarks Found",
                    subtitle="Use 'add <title> <url>' to add first bookmark",
                    icon_markup=icons.info,
                    action=lambda: None,
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={"type": "info", "keep_launcher_open": True},
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
        return results[: self.max_results]

    def _get_recent_bookmarks(self) -> List[Result]:
        """Get recent/popular bookmarks when no query is provided."""
        bookmarks = self.bookmark_manager.get_bookmarks()

        if not bookmarks:
            return [
                Result(
                    title="No Bookmarks Yet",
                    subtitle="Use 'add <title> <url>' to add first bookmark",
                    icon_markup=icons.info,
                    action=lambda: None,
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={"type": "help", "keep_launcher_open": True},
                ),
                Result(
                    title="Example: Add Google",
                    subtitle="add Google https://google.com",
                    icon_markup=icons.bulb,
                    action=lambda: None,
                    relevance=0.9,
                    plugin_name=self.display_name,
                    data={"type": "example", "keep_launcher_open": True},
                ),
            ]

        # Sort by access time (most recent first) and show top 10
        sorted_bookmarks = sorted(
            bookmarks, key=lambda b: b.get("accessed", 0), reverse=True
        )
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
                    data={"type": "help", "keep_launcher_open": True},
                ),
                Result(
                    title="Example",
                    subtitle="add Google https://google.com Search engine",
                    icon_markup=icons.bulb,
                    action=lambda: None,
                    relevance=0.9,
                    plugin_name=self.display_name,
                    data={"type": "example", "keep_launcher_open": True},
                ),
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
                    data={"type": "error", "keep_launcher_open": True},
                )
            ]

        title = parts[0]
        url = parts[1]
        description = " ".join(parts[2:]) if len(parts) > 2 else ""

        # Check if bookmark already exists
        normalized_url = self.bookmark_manager._normalize_url(url)
        existing_bookmarks = self.bookmark_manager.get_bookmarks()
        already_exists = any(
            bookmark["url"] == normalized_url for bookmark in existing_bookmarks
        )

        if already_exists:
            # Truncate URL for display to prevent launcher resize
            display_url = normalized_url
            if len(display_url) > 35:
                display_url = display_url[:32] + "..."

            return [
                Result(
                    title="Bookmark Already Exists",
                    subtitle=f"URL '{display_url}' already exists",
                    icon_markup=icons.alert,
                    action=lambda: None,
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={"type": "error", "keep_launcher_open": True},
                )
            ]

        # Show add action - will execute on Enter
        domain = self.bookmark_manager._extract_domain(normalized_url)

        # Truncate domain if too long
        if len(domain) > 25:
            domain = domain[:22] + "..."

        subtitle = f"Click to add: {domain}"
        if description:
            # Truncate description to prevent launcher resize
            max_desc_len = 35 - len(domain)  # Account for domain + separator
            if len(description) > max_desc_len:
                description = description[:max_desc_len-3] + "..."
            subtitle += f" • {description}"

        # Truncate title for display
        display_title = title
        if len(display_title) > 25:
            display_title = display_title[:22] + "..."

        return [
            Result(
                title=f"Add bookmark '{display_title}'",
                subtitle=subtitle,
                icon_markup=icons.plus,
                action=lambda: self._add_bookmark_action(title, url, description),
                relevance=1.0,
                plugin_name=self.display_name,
                data={"type": "add", "name": title, "keep_launcher_open": True},
            )
        ]

    def _handle_remove_command(self, identifier: str) -> List[Result]:
        """Handle remove bookmark command."""
        if not identifier:
            return self._show_remove_help()

        # Find matching bookmarks
        bookmarks = self.bookmark_manager.get_bookmarks()
        identifier_lower = identifier.lower().strip()

        matching_bookmarks = []
        for bookmark in bookmarks:
            if (
                bookmark["title"].lower() == identifier_lower
                or bookmark["url"].lower() == identifier_lower
                or self.bookmark_manager._extract_domain(bookmark["url"]).lower()
                == identifier_lower
            ):
                matching_bookmarks.append(bookmark)

        if not matching_bookmarks:
            return [
                Result(
                    title="Bookmark Not Found",
                    subtitle=f"No bookmark found matching '{identifier}'",
                    icon_markup=icons.alert,
                    action=lambda: None,
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={"type": "error", "keep_launcher_open": True},
                )
            ]

        # Show remove action - will execute on Enter
        bookmark = matching_bookmarks[0]  # Take first match
        title = bookmark.get("title", "Untitled")
        domain = self.bookmark_manager._extract_domain(bookmark.get("url", ""))

        # Truncate title and domain for display
        display_title = title
        if len(display_title) > 25:
            display_title = display_title[:22] + "..."

        display_domain = domain
        if len(display_domain) > 30:
            display_domain = display_domain[:27] + "..."

        return [
            Result(
                title=f"Remove '{display_title}'?",
                subtitle=f"Click to confirm: {display_domain}",
                icon_markup=icons.trash,
                action=lambda: self._remove_bookmark_action(identifier),
                relevance=1.0,
                plugin_name=self.display_name,
                data={"type": "remove", "name": title, "keep_launcher_open": True},
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
                data={"type": "help", "keep_launcher_open": True},
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
                    data={"type": "info", "keep_launcher_open": True},
                )
            )

            # Show first few bookmarks as examples
            for bookmark in bookmarks[:3]:
                title = bookmark.get("title", "Untitled")
                domain = self._extract_domain(bookmark.get("url", ""))

                # Truncate title and domain for consistent display
                display_title = title
                if len(display_title) > 20:
                    display_title = display_title[:17] + "..."

                display_domain = domain
                if len(display_domain) > 20:
                    display_domain = display_domain[:17] + "..."

                results.append(
                    Result(
                        title=f"remove {display_title}",
                        subtitle=f"Click to remove: {display_title} ({display_domain})",
                        icon_markup=icons.trash,
                        action=lambda t=title: self._remove_bookmark_action(t),
                        relevance=0.8,
                        plugin_name=self.display_name,
                        data={
                            "type": "remove_option",
                            "bookmark": bookmark,
                            "keep_launcher_open": True,
                        },
                    )
                )

        return results

    def _add_bookmark_action(self, title: str, url: str, description: str = ""):
        """Execute the add bookmark action."""
        success = self.bookmark_manager.add_bookmark(title, url, description)
        if success:
            print(f"✓ Added bookmark '{title}' - {url}")
            # Clear cache to force refresh
            self._results_cache.clear()
            self._cache_timestamps.clear()
            # Reset to trigger word and refresh
            self._reset_to_trigger()
        else:
            print(f"✗ Failed to add bookmark '{title}' - already exists")

    def _remove_bookmark_action(self, identifier: str):
        """Execute the remove bookmark action."""
        success = self.bookmark_manager.remove_bookmark(identifier)
        if success:
            print(f"✓ Removed bookmark '{identifier}'")
            # Clear cache to force refresh
            self._results_cache.clear()
            self._cache_timestamps.clear()
            # Reset to trigger word and refresh
            self._reset_to_trigger()
        else:
            print(f"✗ Failed to remove bookmark '{identifier}' - not found")

    def _remove_bookmark_with_reset(self, identifier: str):
        """Execute the remove bookmark action via alt_action (Shift+Enter) and reset to trigger."""
        success = self.bookmark_manager.remove_bookmark(identifier)
        if success:
            print(f"✓ Removed bookmark '{identifier}'")
            # Clear cache to force refresh
            self._results_cache.clear()
            self._cache_timestamps.clear()
            # Reset to trigger word and refresh
            self._reset_to_trigger()
        else:
            print(f"✗ Failed to remove bookmark '{identifier}' - not found")

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

    def _create_bookmark_result(
        self, bookmark: Dict, relevance: float
    ) -> Optional[Result]:
        """Create a Result object for a bookmark."""
        try:
            title = bookmark.get("title", "Untitled")
            url = bookmark.get("url", "")
            description = bookmark.get("description", "")

            # Truncate long titles to prevent launcher resize
            if len(title) > 45:
                title = title[:42] + "..."

            # Create subtitle with domain and description
            domain = self._extract_domain(url)

            # Truncate domain if too long
            if len(domain) > 30:
                domain = domain[:27] + "..."

            if description:
                # Truncate description to prevent launcher resize
                max_desc_len = 50 - len(domain)  # Account for domain + separator
                if len(description) > max_desc_len:
                    description = description[:max_desc_len-3] + "..."
                subtitle = f"{domain} • {description}"
            else:
                subtitle = domain

            # Final subtitle length check to ensure consistent launcher size
            if len(subtitle) > 60:
                subtitle = subtitle[:57] + "..."

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
                    "description": description,
                    "keep_launcher_open": False,
                    "alt_action": lambda t=title: self._remove_bookmark_with_reset(t),
                },
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
                ["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except Exception as e:
            print(f"Failed to open bookmark: {e}")

    def _setup_launcher_hooks(self):
        """Setup hooks to monitor launcher state."""
        try:
            # Try to find the launcher instance
            import gc

            for obj in gc.get_objects():
                if (
                    hasattr(obj, "__class__")
                    and obj.__class__.__name__ == "Launcher"
                    and hasattr(obj, "close_launcher")
                ):
                    self._launcher_instance = obj
                    break
        except Exception as e:
            print(f"Warning: Could not setup launcher hooks: {e}")

    def _cleanup_launcher_hooks(self):
        """Cleanup launcher hooks."""
        try:
            self._launcher_instance = None
        except Exception as e:
            print(f"Warning: Could not cleanup launcher hooks: {e}")

    def _reset_to_trigger(self):
        """Reset launcher to trigger word and refresh."""
        try:
            if self._launcher_instance and hasattr(
                self._launcher_instance, "search_entry"
            ):
                # Get the current trigger (bookmark or bm)
                current_text = self._launcher_instance.search_entry.get_text()
                trigger = "bookmark "

                # Determine which trigger was used
                if current_text.lower().startswith("bm "):
                    trigger = "bm "

                # Reset to trigger word with space
                try:
                    from gi.repository import GLib

                    def reset_and_refresh():
                        # Set text to trigger word
                        self._launcher_instance.search_entry.set_text(trigger)
                        # Position cursor at end
                        self._launcher_instance.search_entry.set_position(-1)
                        # Trigger search to show default bookmarks
                        self._launcher_instance._perform_search(trigger)
                        return False

                    GLib.timeout_add(50, reset_and_refresh)
                except ImportError:
                    # Fallback: direct call if GLib not available
                    self._launcher_instance.search_entry.set_text(trigger)
                    self._launcher_instance.search_entry.set_position(-1)
                    self._launcher_instance._perform_search(trigger)
        except Exception as e:
            print(f"Could not reset to trigger: {e}")

    def _force_launcher_refresh(self):
        """Force the launcher to refresh and show updated results."""
        try:
            if self._launcher_instance and hasattr(
                self._launcher_instance, "_perform_search"
            ):
                # Get current search text
                current_text = ""
                if hasattr(self._launcher_instance, "search_entry"):
                    current_text = self._launcher_instance.search_entry.get_text()

                # Trigger a search to refresh results
                try:
                    from gi.repository import GLib

                    def refresh():
                        self._launcher_instance._perform_search(current_text)
                        return False

                    GLib.timeout_add(50, refresh)
                except ImportError:
                    # Fallback: direct call if GLib not available
                    self._launcher_instance._perform_search(current_text)
        except Exception as e:
            print(f"Could not force launcher refresh: {e}")
