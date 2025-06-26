import os
import shlex
import time
from typing import List, Union

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
        self.set_triggers(["bin"])
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
        self._update_bin_cache()
        for binary in self._bin_cache:
            if binary_query in binary.lower():
                relevance = self._calculate_binary_relevance(binary, binary_query)
                if relevance > 0:
                    # If the query starts with this binary, use the full command
                    if binary.lower() == binary_query:
                        # Exact binary match - use full command with arguments
                        display_command = full_command
                        command_to_execute = full_command
                    elif binary.lower().startswith(binary_query):
                        # Binary starts with query - suggest the binary name only
                        display_command = binary
                        command_to_execute = binary
                    else:
                        # Partial match - suggest the binary name only
                        display_command = binary
                        command_to_execute = binary

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
            import traceback

            traceback.print_exc()
