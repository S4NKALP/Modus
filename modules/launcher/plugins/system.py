"""
System plugin for the launcher.
Provides system commands and actions.
"""

import os
import time
from typing import List

from fabric.utils import exec_shell_command_async
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

        # Cache for system binaries
        self._bin_cache = set()
        self._last_bin_update = 0
        self._bin_update_interval = 300  # 5 minutes

    def initialize(self):
        """Initialize the system plugin."""
        # Set up triggers for system commands
        self.set_triggers(["bin", "bin "])
        self._update_bin_cache()

    def cleanup(self):
        """Cleanup the system plugin."""
        self._bin_cache.clear()

    def _update_bin_cache(self):
        """Update the cache of available system binaries."""
        current_time = time.time()
        if current_time - self._last_bin_update > self._bin_update_interval:
            self._bin_cache.clear()
            for path in os.environ["PATH"].split(":"):
                if os.path.exists(path):
                    try:
                        for file in os.listdir(path):
                            if os.access(os.path.join(path, file), os.X_OK):
                                self._bin_cache.add(file)
                    except (PermissionError, FileNotFoundError):
                        continue
            self._last_bin_update = current_time

    def query(self, query_string: str) -> List[Result]:
        """Search for system commands matching the query."""
        query = query_string.lower().strip()

        if not query:
            return []

        results = []

        # Check system binaries
        self._update_bin_cache()
        for binary in self._bin_cache:
            if query in binary.lower():
                relevance = self._calculate_binary_relevance(binary, query)
                if relevance > 0:
                    result = Result(
                        title=binary,
                        subtitle=f"Execute {binary}",
                        icon_markup=icons.terminal,
                        action=lambda b=binary: self._execute_command([b]),
                        relevance=relevance,
                        plugin_name=self.display_name,
                        data={"command": [binary], "id": binary},
                    )
                    results.append(result)

        return sorted(results, key=lambda x: x.relevance, reverse=True)

    def _calculate_binary_relevance(self, binary: str, query: str) -> float:
        """Calculate relevance score for a binary."""
        binary_lower = binary.lower()

        # Exact match
        if query == binary_lower:
            return 1.0

        # Starts with query
        if binary_lower.startswith(query):
            return 0.9

        # Contains query
        if query in binary_lower:
            return 0.7

        return 0.0

    def _execute_command(self, command: List[str]):
        """Execute a system command."""
        exec_shell_command_async(command)
