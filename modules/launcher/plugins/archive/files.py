import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List

from thefuzz import fuzz

import utils.icons as icons
from modules.launcher.plugin_base import PluginBase
from modules.launcher.result import Result


class FilesPlugin(PluginBase):
    """
    High-performance plugin for searching files only (excludes directories).
    Uses advanced fuzzy matching, caching, and threading for optimal performance.
    """

    def __init__(self):
        super().__init__()
        self.display_name = "Files"
        self.description = "Search for files only"

        # Performance-optimized search paths - focus on user directories
        self.search_paths = [
            os.path.expanduser("~/Documents"),
            os.path.expanduser("~/Downloads"),
            os.path.expanduser("~/Desktop"),
            os.path.expanduser("~/Pictures"),
            os.path.expanduser("~/Videos"),
            os.path.expanduser("~/Music"),
            os.path.expanduser("~"),  # Home directory but with limited depth
        ]

        # Performance settings
        self.max_results = 15
        self.max_depth = 2  # Reduced depth for better performance
        self.search_timeout = 0.5  # Reduced timeout
        self.min_query_length = 1  # Allow single character searches

        # Fuzzy search settings - optimized for performance
        self.fuzzy_thresholds = {
            "ratio": 70,  # Increased for better precision
            "partial": 80,  # Increased for better precision
            "token_sort": 75,  # Increased for better precision
            "token_set": 75,  # Increased for better precision
        }

        # Enhanced caching
        self.file_cache: Dict[str, List[str]] = {}
        self.cache_timestamp: Dict[str, float] = {}
        self.cache_ttl = 300
        self.cache_lock = threading.Lock()

        # Thread pool for concurrent searches
        self.executor = ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="files-search"
        )

    def initialize(self):
        """Initialize the files plugin."""
        self.set_triggers(
            [
                "file",
                "find",
            ]
        )
        self._warm_cache()

    def cleanup(self):
        """Cleanup the files plugin."""
        if hasattr(self, "executor"):
            self.executor.shutdown(wait=False)
        with self.cache_lock:
            self.file_cache.clear()
            self.cache_timestamp.clear()

    def query(self, query_string: str) -> List[Result]:
        """Fast search for files matching the query."""
        query = query_string.strip()

        if len(query) < self.min_query_length:
            return []

        # Handle special path queries
        if query.startswith("/") or query.startswith("~"):
            return self._handle_path_query(query)

        # Always search for files only since this is the files plugin
        # triggered by "file" or "find" keywords
        is_file_only = True

        # Use cached search for better performance
        results = self._fast_search(query, file_only=is_file_only)

        # Sort by relevance and limit results
        results.sort(key=lambda r: r.relevance, reverse=True)
        return results[: self.max_results]

    def _warm_cache(self):
        """Pre-warm cache for common directories in background."""

        def warm_directory(path):
            try:
                if os.path.exists(path) and os.path.isdir(path):
                    self._get_cached_files(path)
            except:
                pass

        for path in self.search_paths:
            threading.Thread(target=warm_directory, args=(path,), daemon=True).start()

    def _handle_path_query(self, query: str) -> List[Result]:
        """Handle path-based queries like '/home' or '~/Documents'."""
        try:
            expanded_path = (
                os.path.expanduser(query) if query.startswith("~") else query
            )

            if os.path.isdir(expanded_path):
                return self._list_directory_contents(expanded_path)

            parent_dir = os.path.dirname(expanded_path)
            if os.path.isdir(parent_dir):
                basename = os.path.basename(expanded_path)
                return self._search_in_directory(parent_dir, basename, max_results=10)

        except Exception:
            pass

        return []

    def _fast_search(self, query: str, file_only: bool = False) -> List[Result]:
        """Fast search using cached file lists and optimized matching."""
        results = []
        query_lower = query.lower()

        # Early exit for empty queries
        if len(query_lower) < self.min_query_length:
            return results

        # Search in cached directories with early termination
        for search_path in self.search_paths:
            if not os.path.exists(search_path):
                continue

            # Skip home directory if we already have enough results from specific folders
            if (
                search_path == os.path.expanduser("~")
                and len(results) >= self.max_results
            ):
                continue

            cached_files = self._get_cached_files(search_path)
            for file_path in cached_files:
                if file_only and os.path.isdir(file_path):
                    continue

                filename = os.path.basename(file_path)

                # Fast pre-filter: check if query is in filename before expensive fuzzy matching
                if query_lower not in filename.lower():
                    # Only do fuzzy matching if simple substring match fails
                    if not self._simple_fuzzy_match(query_lower, filename):
                        continue

                relevance = self._calculate_relevance(filename, query_lower)
                result = self._create_file_result(file_path, relevance)
                if result:
                    results.append(result)

                # Early termination when we have enough results
                if len(results) >= self.max_results * 3:
                    return results

        return results

    def _get_cached_files(self, directory: str) -> List[str]:
        """Get cached file list for directory, refresh if needed."""
        current_time = time.time()

        with self.cache_lock:
            if (
                directory in self.file_cache
                and directory in self.cache_timestamp
                and current_time - self.cache_timestamp[directory] < self.cache_ttl
            ):
                return self.file_cache[directory]

            files = self._scan_directory_fast(directory)
            self.file_cache[directory] = files
            self.cache_timestamp[directory] = current_time

        return files

    def _scan_directory_fast(self, directory: str) -> List[str]:
        """Fast directory scan with optimized depth and early termination."""
        files = []
        current_depth = 0
        max_files_per_dir = 1000  # Limit files per directory to prevent memory issues

        def scan_dir(path: str, depth: int):
            if depth > self.max_depth or len(files) >= max_files_per_dir:
                return

            try:
                with os.scandir(path) as entries:
                    for entry in entries:
                        try:
                            if entry.name.startswith("."):
                                continue

                            # Skip common large directories that are unlikely to contain user files
                            if entry.is_dir() and entry.name in {
                                "node_modules",
                                ".git",
                                ".cache",
                                "__pycache__",
                                ".npm",
                                ".cargo",
                                ".rustup",
                                "target",
                                "build",
                                ".vscode",
                                ".idea",
                                "venv",
                                ".env",
                            }:
                                continue

                            files.append(entry.path)

                            # Early termination if we have too many files
                            if len(files) >= max_files_per_dir:
                                return

                            # Only recurse into directories if we're not at max depth
                            # and for home directory, be more selective
                            if entry.is_dir() and depth < self.max_depth:
                                if path == os.path.expanduser("~"):
                                    # For home directory, only scan important subdirectories
                                    if self._is_important_directory(entry.name):
                                        scan_dir(entry.path, depth + 1)
                                else:
                                    scan_dir(entry.path, depth + 1)

                        except (PermissionError, OSError):
                            continue
            except (PermissionError, OSError):
                pass

        scan_dir(directory, current_depth)
        return files

    def _is_important_directory(self, dirname: str) -> bool:
        """Check if directory is important enough to scan deeper."""
        important_dirs = {
            "Documents",
            "Downloads",
            "Desktop",
            "Pictures",
            "Videos",
            "Music",
            "Projects",
            "Code",
            "Development",
            "Work",
            "src",
            "bin",
        }
        return dirname in important_dirs

    def _search_in_directory(
        self, directory: str, query: str, max_results: int = 10
    ) -> List[Result]:
        """Search for files in a specific directory."""
        results = []
        query_lower = query.lower()

        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if self._simple_fuzzy_match(query_lower, entry.name):
                        relevance = self._calculate_relevance(entry.name, query_lower)
                        result = self._create_file_result(entry.path, relevance)
                        if result:
                            results.append(result)

                    if len(results) >= max_results:
                        break
        except (PermissionError, OSError):
            pass

        return results

    def _list_directory_contents(
        self, directory: str, max_results: int = 15
    ) -> List[Result]:
        """List contents of a directory."""
        results = []

        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if not entry.name.startswith("."):
                        result = self._create_file_result(entry.path, 0.8)
                        if result:
                            results.append(result)

                    if len(results) >= max_results:
                        break
        except (PermissionError, OSError):
            pass

        return results

    def _create_file_result(self, file_path: str, relevance: float) -> Result:
        """Create a Result object for a file or directory."""
        try:
            filename = os.path.basename(file_path)
            is_dir = os.path.isdir(file_path)

            return Result(
                title=filename,
                subtitle=file_path,
                icon_markup=icons.file,
                action=lambda p=file_path: self._open_path(p),
                relevance=relevance,
                plugin_name=self.display_name,
                data={"path": file_path, "type": "directory" if is_dir else "file"},
            )
        except Exception:
            return None

    def _open_path(self, path: str):
        """Open a file or directory with the default application."""
        try:
            subprocess.Popen(
                ["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except Exception as e:
            print(f"Failed to open {path}: {e}")

    def _open_file(self, file_path: str):
        """Open a file with the default application."""
        self._open_path(file_path)

    def _open_directory(self, dir_path: str):
        """Open a directory in the file manager."""
        self._open_path(dir_path)

    def _simple_fuzzy_match(self, query: str, text: str) -> bool:
        """Optimized fuzzy matching with performance improvements."""
        text_lower = text.lower()
        query_lower = query.lower()

        # Fast exact substring match
        if query_lower in text_lower:
            return True

        # Fast prefix match
        if text_lower.startswith(query_lower):
            return True

        # Only do expensive fuzzy matching for longer queries
        if len(query_lower) >= 3:
            # Use only the most effective fuzzy matching methods
            return (
                fuzz.partial_ratio(query_lower, text_lower)
                >= self.fuzzy_thresholds["partial"]
                or fuzz.ratio(query_lower, text_lower) >= self.fuzzy_thresholds["ratio"]
            )

        return False

    def _calculate_relevance(self, filename: str, query: str) -> float:
        """Calculate relevance score with optimized performance."""
        filename_lower = filename.lower()
        query_lower = query.lower()

        # Fast exact match
        if query_lower == filename_lower:
            return 1.0

        # Fast prefix match
        if filename_lower.startswith(query_lower):
            return 0.95

        # Fast substring match
        if query_lower in filename_lower:
            # Calculate position-based relevance
            position = filename_lower.index(query_lower)
            position_score = 1.0 - (position / len(filename_lower))
            return 0.8 + (position_score * 0.1)

        # Only do expensive fuzzy matching for longer queries
        if len(query_lower) >= 3:
            partial = fuzz.partial_ratio(query_lower, filename_lower)
            ratio = fuzz.ratio(query_lower, filename_lower)

            # Simplified relevance calculation
            relevance = (partial * 0.6 + ratio * 0.4) / 100.0
            return max(relevance, 0.3)  # Minimum relevance for fuzzy matches

        return 0.3  # Default relevance for short queries
