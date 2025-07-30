import json
import os
import shlex
import threading
import time
from typing import List, Set, Union

from fabric.utils import exec_shell_command_async

import config.data as data
import utils.icons as icons
from modules.launcher.plugin_base import PluginBase
from modules.launcher.result import Result


class SystemPlugin(PluginBase):
    """
    Plugin for system commands and actions.
    """

    def __init__(self):
        super().__init__()
        self.display_name = "System"
        self.description = "System commands and actions"

        # JSON cache file for system binaries
        self.bin_cache_file = os.path.join(data.CACHE_DIR, "system_binaries.json")

        # In-memory cache for system binaries
        self._bin_cache: Set[str] = set()
        self._last_bin_update = 0
        self._bin_update_interval = 300  # 5 minutes

        # Background cache building
        self._cache_building = False
        self._cache_thread = None

    def initialize(self):
        """Initialize the system plugin."""
        self.set_triggers(["bin"])
        self._load_bin_cache()
        self._start_background_cache_update()

    def cleanup(self):
        """Cleanup the system plugin."""
        self._bin_cache.clear()
        if self._cache_thread and self._cache_thread.is_alive():
            # Note: We don't join the thread to avoid blocking cleanup
            pass

    def _load_bin_cache(self):
        """Load binary cache from JSON file."""
        try:
            if os.path.exists(self.bin_cache_file):
                with open(self.bin_cache_file, "r", encoding="utf-8") as f:
                    cache_data = json.load(f)
                    self._bin_cache = set(cache_data.get("binaries", []))
                    self._last_bin_update = cache_data.get("last_update", 0)
            else:
                print(
                    "SystemPlugin: No cache file found, will build cache in background"
                )
        except Exception as e:
            print(f"SystemPlugin: Error loading binary cache: {e}")
            self._bin_cache = set()
            self._last_bin_update = 0

    def _save_bin_cache(self):
        """Save binary cache to JSON file."""
        try:
            # Ensure the cache directory exists
            os.makedirs(data.CACHE_DIR, exist_ok=True)

            cache_data = {
                "binaries": sorted(list(self._bin_cache)),
                "last_update": self._last_bin_update,
                "cache_version": "1.0",
            }

            with open(self.bin_cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2)
        except Exception as e:
            print(f"SystemPlugin: Error saving binary cache: {e}")

    def _start_background_cache_update(self):
        """Start background thread to update binary cache."""
        current_time = time.time()

        # Check if cache needs updating
        if (
            current_time - self._last_bin_update > self._bin_update_interval
            or not self._bin_cache
        ):

            if not self._cache_building:
                self._cache_building = True
                self._cache_thread = threading.Thread(
                    target=self._build_bin_cache_background, daemon=True
                )
                self._cache_thread.start()

    def _build_bin_cache_background(self):
        """Build binary cache in background thread."""
        try:
            new_cache = set()
            processed_paths = set()  # Avoid duplicate paths

            for path in os.environ["PATH"].split(":"):
                # Skip empty paths and duplicates
                if not path or path in processed_paths:
                    continue
                processed_paths.add(path)

                if os.path.exists(path) and os.path.isdir(path):
                    try:
                        # Use os.scandir for better performance than os.listdir
                        with os.scandir(path) as entries:
                            for entry in entries:
                                if entry.is_file(follow_symlinks=False) and os.access(
                                    entry.path, os.X_OK
                                ):
                                    new_cache.add(entry.name)
                    except (PermissionError, FileNotFoundError, OSError):
                        continue

            # Update cache atomically
            self._bin_cache = new_cache
            self._last_bin_update = time.time()

            # Save to disk
            self._save_bin_cache()

        except Exception as e:
            print(f"SystemPlugin: Error building binary cache: {e}")
        finally:
            self._cache_building = False

    def query(self, query_string: str) -> List[Result]:
        """Search for system commands matching the query."""
        query = query_string.strip()

        if not query:
            return []

        results = []

        # Parse the query to extract binary name and arguments
        query_parts = query.split()
        if not query_parts:
            return []

        binary_query = query_parts[0].lower()
        full_command = query  # Keep the original case and spacing

        # Check system binaries
        # Start background update if needed (non-blocking) - but only if cache is empty or very old
        if not self._bin_cache or (
            time.time() - self._last_bin_update > self._bin_update_interval
        ):
            self._start_background_cache_update()

        # Optimize search with early termination and result limiting
        exact_matches = []
        prefix_matches = []
        partial_matches = []
        max_results = 20  # Limit total results for performance

        for binary in self._bin_cache:
            # Pre-compute lowercase once
            binary_lower = binary.lower()

            # Skip if no match at all
            if binary_query not in binary_lower:
                continue

            # Categorize matches for better sorting
            if binary_lower == binary_query:
                # Exact match - highest priority
                display_command = full_command
                command_to_execute = full_command
                relevance = 1.0
                exact_matches.append(
                    (binary, display_command, command_to_execute, relevance)
                )
            elif binary_lower.startswith(binary_query):
                # Prefix match - high priority
                display_command = binary
                command_to_execute = binary
                relevance = 0.9
                prefix_matches.append(
                    (binary, display_command, command_to_execute, relevance)
                )
            else:
                # Partial match - lower priority
                display_command = binary
                command_to_execute = binary
                relevance = 0.7
                partial_matches.append(
                    (binary, display_command, command_to_execute, relevance)
                )

            # Early termination if we have enough good matches
            if len(exact_matches) + len(prefix_matches) >= max_results:
                break

        # Combine results in priority order
        all_matches = exact_matches + prefix_matches + partial_matches

        # Convert to Result objects (limit to max_results)
        for binary, display_command, command_to_execute, relevance in all_matches[
            :max_results
        ]:
            result = Result(
                title=display_command,
                subtitle=f"Execute: {display_command}",
                icon_markup=icons.terminal,
                action=self._create_action(command_to_execute),
                relevance=relevance,
                plugin_name=self.display_name,
                data={"command": command_to_execute, "id": binary},
            )
            results.append(result)

        return results  # Already sorted by priority

    def _create_action(self, command: Union[str, List[str]]):
        """Create an action function for the given command."""

        def action():
            self._execute_command(command)

        return action

    def _execute_command(self, command: Union[str, List[str]]):
        """Execute a system command."""
        try:
            if isinstance(command, str):
                # Handle string commands with arguments - split into list for proper execution
                command_list = shlex.split(command)
                exec_shell_command_async(command_list)
            else:
                # Handle list commands (backward compatibility)
                exec_shell_command_async(command)
        except Exception as e:
            print(f"SystemPlugin: Error executing command '{command}': {e}")
