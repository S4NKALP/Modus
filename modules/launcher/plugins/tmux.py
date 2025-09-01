import subprocess
import threading
import time
from typing import List

import config.data as data
from fabric.utils import exec_shell_command_async
from modules.launcher.plugin_base import PluginBase
from modules.launcher.result import Result


class TmuxPlugin(PluginBase):
    """
    Plugin for managing tmux sessions through the launcher.
    """

    def __init__(self):
        super().__init__()
        self.display_name = "Tmux Manager"
        self.description = "Manage tmux sessions - create, attach, rename, and kill"

        # Cache for sessions to avoid repeated subprocess calls
        self._sessions_cache = []
        self._last_cache_update = 0
        # Cache sessions for 10 seconds (increased from 2)
        self._cache_ttl = 10

        # Threading for auto-refresh - only when actively used
        self.refresh_thread = None
        self.stop_refresh = threading.Event()
        self._last_query_time = 0
        # Stop refreshing after 30 seconds of inactivity
        self._active_refresh_timeout = 30

    def initialize(self):
        """Initialize the tmux plugin."""
        self.set_triggers(["tmux"])
        # Don't start refresh thread immediately - start it when first used

    def cleanup(self):
        """Cleanup the tmux plugin."""
        self.stop_refresh.set()
        if self.refresh_thread:
            self.refresh_thread.join(timeout=1)
        self._sessions_cache.clear()

    def _start_refresh_thread(self):
        """Start background thread to refresh session cache."""
        if not self.refresh_thread or not self.refresh_thread.is_alive():
            self.refresh_thread = threading.Thread(
                target=self._refresh_sessions_background, daemon=True
            )
            self.refresh_thread.start()

    def _refresh_sessions_background(self):
        """Background thread to refresh sessions cache only when actively used."""
        while not self.stop_refresh.is_set():
            try:
                current_time = time.time()

                # Stop refreshing if plugin hasn't been used recently
                if current_time - self._last_query_time > self._active_refresh_timeout:
                    print("TmuxPlugin: Stopping background refresh due to inactivity")
                    break

                if current_time - self._last_cache_update > self._cache_ttl:
                    self._sessions_cache = self._get_tmux_sessions()
                    self._last_cache_update = current_time

                self.stop_refresh.wait(5)
            except Exception as e:
                print(f"TmuxPlugin: Error in refresh thread: {e}")
                self.stop_refresh.wait(10)  # Wait longer on error

    def _get_tmux_sessions(self):
        """Get list of tmux sessions."""
        try:
            result = subprocess.run(
                ["tmux", "list-sessions", "-F", "#{session_name}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return [
                    s.strip() for s in result.stdout.strip().split("\n") if s.strip()
                ]
            return []
        except (
            subprocess.TimeoutExpired,
            subprocess.CalledProcessError,
            FileNotFoundError,
        ) as e:
            print(f"TmuxPlugin: Error getting tmux sessions: {e}")
            return []

    def query(self, query_string: str) -> List[Result]:
        """Process tmux queries."""
        query = query_string.strip().lower()
        results = []

        # Track usage and start refresh thread if needed
        current_time = time.time()
        self._last_query_time = current_time

        # Start refresh thread if not running and plugin is being used
        if not self.refresh_thread or not self.refresh_thread.is_alive():
            self._start_refresh_thread()

        # Get current sessions (use cache if recent)
        if current_time - self._last_cache_update > self._cache_ttl:
            self._sessions_cache = self._get_tmux_sessions()
            self._last_cache_update = current_time

        sessions = self._sessions_cache

        # Handle specific commands
        if query.startswith("new ") or query.startswith("create "):
            session_name = query.split(" ", 1)[1].strip() if " " in query else ""
            results.append(self._create_new_session_result(session_name))

        elif query.startswith("kill ") or query.startswith("delete "):
            session_name = query.split(" ", 1)[1].strip() if " " in query else ""
            if session_name:
                matching_sessions = [
                    s for s in sessions if session_name.lower() in s.lower()
                ]
                for session in matching_sessions:
                    results.append(self._create_kill_session_result(session))

        elif query.startswith("rename "):
            parts = query.split(" ", 2)
            if len(parts) >= 3:
                old_name, new_name = parts[1], parts[2]
                if old_name in sessions:
                    results.append(
                        self._create_rename_session_result(old_name, new_name)
                    )

        else:
            # Show existing sessions for attachment
            if sessions:
                # Filter sessions based on query
                if query:
                    filtered_sessions = [s for s in sessions if query in s.lower()]
                else:
                    filtered_sessions = sessions

                for session in filtered_sessions:
                    results.append(self._create_attach_session_result(session))

            # Always show option to create new session
            if not query or "new" in query or "create" in query:
                results.append(
                    self._create_new_session_result(
                        query
                        if query and not any(cmd in query for cmd in ["new", "create"])
                        else ""
                    )
                )

        return results

    def _create_attach_session_result(self, session_name: str) -> Result:
        """Create result for attaching to a session."""
        return Result(
            title=f"Attach to '{session_name}'",
            subtitle=f"Connect to tmux session: {session_name}",
            icon_name="terminal",
            action=lambda: self._attach_to_session(session_name),
            relevance=0.9,
            data={"type": "attach", "session": session_name},
        )

    def _create_new_session_result(self, session_name: str = "") -> Result:
        """Create result for creating a new session."""
        display_name = session_name if session_name else "new session"
        return Result(
            title=f"Create '{display_name}'",
            subtitle=f"Create new tmux session{
                f': {session_name}' if session_name else ''
            }",
            icon_name="plus",
            action=lambda: self._create_session(session_name),
            relevance=0.8,
            data={"type": "create", "session": session_name},
        )

    def _create_kill_session_result(self, session_name: str) -> Result:
        """Create result for killing a session."""
        return Result(
            title=f"Kill '{session_name}'",
            subtitle=f"Terminate tmux session: {session_name}",
            icon_name="trash",
            action=lambda: self._kill_session(session_name),
            relevance=0.7,
            data={"type": "kill", "session": session_name},
        )

    def _create_rename_session_result(self, old_name: str, new_name: str) -> Result:
        """Create result for renaming a session."""
        return Result(
            title=f"Rename '{old_name}' to '{new_name}'",
            subtitle=f"Rename tmux session from {old_name} to {new_name}",
            icon_name="config",
            action=lambda: self._rename_session(old_name, new_name),
            relevance=0.6,
            data={"type": "rename", "old_session": old_name, "new_session": new_name},
        )

    def _attach_to_session(self, session_name: str):
        """Attach to an existing tmux session."""
        try:
            terminal_cmd = self._get_terminal_command(
                f"tmux attach-session -t '{session_name}'"
            )
            exec_shell_command_async(terminal_cmd)
            print(f"TmuxPlugin: Attaching to session '{session_name}'")
        except Exception as e:
            print(f"TmuxPlugin: Error attaching to session '{session_name}': {e}")

    def _create_session(self, session_name: str = ""):
        """Create a new tmux session."""
        try:
            if not session_name:
                # Generate a default name
                existing_sessions = self._get_tmux_sessions()
                counter = 0
                while str(counter) in existing_sessions:
                    counter += 1
                session_name = str(counter)

            # Clean the session name
            clean_name = session_name.strip().replace(" ", "_")

            # Create session
            subprocess.run(
                ["tmux", "new-session", "-d", "-s", clean_name], check=True, timeout=10
            )

            # Launch terminal and attach
            terminal_cmd = self._get_terminal_command(
                f"tmux attach-session -t '{clean_name}'"
            )
            exec_shell_command_async(terminal_cmd)

            # Refresh cache
            self._sessions_cache = self._get_tmux_sessions()
            self._last_cache_update = time.time()

            print(f"TmuxPlugin: Created and attached to session '{clean_name}'")
        except Exception as e:
            print(f"TmuxPlugin: Error creating session '{session_name}': {e}")

    def _kill_session(self, session_name: str):
        """Kill a tmux session."""
        try:
            subprocess.run(
                ["tmux", "kill-session", "-t", session_name], check=True, timeout=10
            )

            # Refresh cache
            self._sessions_cache = self._get_tmux_sessions()
            self._last_cache_update = time.time()

            print(f"TmuxPlugin: Killed session '{session_name}'")
        except Exception as e:
            print(f"TmuxPlugin: Error killing session '{session_name}': {e}")

    def _rename_session(self, old_name: str, new_name: str):
        """Rename a tmux session."""
        try:
            clean_name = new_name.strip().replace(" ", "_")
            subprocess.run(
                ["tmux", "rename-session", "-t", old_name, clean_name],
                check=True,
                timeout=10,
            )

            # Refresh cache
            self._sessions_cache = self._get_tmux_sessions()
            self._last_cache_update = time.time()

            print(f"TmuxPlugin: Renamed session '{old_name}' to '{clean_name}'")
        except Exception as e:
            print(
                f"TmuxPlugin: Error renaming session '{old_name}' to '{new_name}': {e}"
            )

    def _get_terminal_command(self, cmd: str) -> str:
        """Get terminal command based on configured terminal or available terminals."""
        # First try to use the configured terminal command
        if hasattr(data, "TERMINAL_COMMAND") and data.TERMINAL_COMMAND:
            parts = data.TERMINAL_COMMAND.split()
            terminal = parts[0]

            try:
                # Check if the configured terminal is available
                subprocess.run(
                    ["which", terminal],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                return f"{data.TERMINAL_COMMAND} {cmd}"
            except subprocess.CalledProcessError:
                # If configured terminal is not available, fall back to defaults
                pass

        # Fallback to checking available terminals
        terminals = [
            ("kitty", f"kitty -e {cmd}"),
            ("alacritty", f"alacritty -e {cmd}"),
            ("foot", f"foot {cmd}"),
            ("gnome-terminal", f"gnome-terminal -- {cmd}"),
            ("konsole", f"konsole -e {cmd}"),
            ("xfce4-terminal", f"xfce4-terminal -e '{cmd}'"),
        ]

        for term, term_cmd in terminals:
            try:
                # Check if terminal is available
                subprocess.run(
                    ["which", term],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                return term_cmd
            except subprocess.CalledProcessError:
                continue

        # Default fallback
        return f"kitty -e {cmd}"
