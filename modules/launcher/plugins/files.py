"""
Files plugin for the launcher.
High-performance file and directory search using advanced fuzzy matching.
"""

import os
import subprocess
import threading
import time
from typing import List, Dict, Set, Tuple
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from thefuzz import fuzz
from ..plugin_base import PluginBase
from ..result import Result
import utils.icons as icons


class FilesPlugin(PluginBase):
    """
    High-performance plugin for searching files and directories.
    Uses advanced fuzzy matching, caching, and threading for optimal performance.
    """

    def __init__(self):
        super().__init__()
        self.display_name = "Files"
        self.description = "Search for files and directories"

        # Performance-optimized search paths
        self.search_paths = [
            os.path.expanduser("~"),
            os.path.expanduser("/"),
        ]

        # Performance settings
        self.max_results = 15
        self.max_depth = 3
        self.search_timeout = 0.8
        self.min_query_length = 1

        # Fuzzy search settings
        self.fuzzy_thresholds = {
            "ratio": 60,
            "partial": 70,
            "token_sort": 65,
            "token_set": 65,
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
                "/",
                "file ",
                "find ",
                "/ ",
            ]
        )
        print("Initializing Files plugin...")
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

        # Check if this is a file-only search
        is_file_only = query.startswith("file ")
        if is_file_only:
            query = query[5:].strip()

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
        """Fast search using cached file lists and concurrent processing."""
        results = []
        query_lower = query.lower()

        # Search in cached directories
        for search_path in self.search_paths:
            if not os.path.exists(search_path):
                continue

            cached_files = self._get_cached_files(search_path)
            for file_path in cached_files:
                if file_only and os.path.isdir(file_path):
                    continue

                filename = os.path.basename(file_path)
                if self._simple_fuzzy_match(query_lower, filename):
                    relevance = self._calculate_relevance(filename, query_lower)
                    result = self._create_file_result(file_path, relevance)
                    if result:
                        results.append(result)

                if len(results) >= self.max_results * 2:
                    break

            if len(results) >= self.max_results * 2:
                break

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
        """Fast directory scan with improved depth and fuzzy search."""
        files = []
        current_depth = 0

        def scan_dir(path: str, depth: int):
            if depth > self.max_depth:
                return

            try:
                with os.scandir(path) as entries:
                    for entry in entries:
                        try:
                            if entry.name.startswith("."):
                                continue

                            files.append(entry.path)

                            if entry.is_dir():
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
            print(f"Opened: {path}")
        except Exception as e:
            print(f"Failed to open {path}: {e}")

    def _open_file(self, file_path: str):
        """Open a file with the default application."""
        self._open_path(file_path)

    def _open_directory(self, dir_path: str):
        """Open a directory in the file manager."""
        self._open_path(dir_path)

    def _simple_fuzzy_match(self, query: str, text: str) -> bool:
        """Advanced fuzzy matching using multiple methods."""
        text_lower = text.lower()
        query_lower = query.lower()

        if query_lower in text_lower:
            return True

        return (
            fuzz.ratio(query_lower, text_lower) >= self.fuzzy_thresholds["ratio"]
            or fuzz.partial_ratio(query_lower, text_lower)
            >= self.fuzzy_thresholds["partial"]
            or fuzz.token_sort_ratio(query_lower, text_lower)
            >= self.fuzzy_thresholds["token_sort"]
            or fuzz.token_set_ratio(query_lower, text_lower)
            >= self.fuzzy_thresholds["token_set"]
        )

    def _calculate_relevance(self, filename: str, query: str) -> float:
        """Calculate relevance score using multiple fuzzy matching methods."""
        filename_lower = filename.lower()
        query_lower = query.lower()

        ratio = fuzz.ratio(query_lower, filename_lower)
        partial = fuzz.partial_ratio(query_lower, filename_lower)
        token_sort = fuzz.token_sort_ratio(query_lower, filename_lower)
        token_set = fuzz.token_set_ratio(query_lower, filename_lower)

        relevance = (
            ratio * 0.2 + partial * 0.4 + token_sort * 0.2 + token_set * 0.2
        ) / 100.0

        if query_lower == filename_lower:
            relevance = 1.0
        elif filename_lower.startswith(query_lower):
            relevance = max(relevance, 0.9)
        elif query_lower in filename_lower:
            relevance = max(relevance, 0.8)

        return relevance
