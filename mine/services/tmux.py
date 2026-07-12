import threading
from pathlib import Path

from fabric.core.service import Property, Service, Signal
from fabric.utils import exec_shell_command_async, idle_add, logger, os

from utils.functions import (
    run_command,
    terminal_open_in_directory_command,
)


class TmuxService(Service):
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @staticmethod
    def get_initial():
        if TmuxService._instance is None:
            TmuxService._instance = TmuxService()
        return TmuxService._instance

    @Signal
    def sessions_changed(self) -> None:
        pass

    def __init__(self, **kwargs):
        if hasattr(self, "_initialized") and self._initialized:
            return
        super().__init__(**kwargs)
        self._initialized = True
        self._sessions: dict[str, str] = {}
        self._monitor_thread = None
        self._stop_monitoring = threading.Event()
        self._last_sessions_hash = None
        self._monitoring_started = False
        self._tmux_available = None  # Cache tmux availability check

        # Don't scan sessions during init to avoid blocking
        # This will be done when monitoring starts

    def _is_tmux_available(self) -> bool:
        if self._tmux_available is None:
            self._tmux_available = (
                run_command(["tmux", "-V"], timeout=5).returncode == 0
            )
        return self._tmux_available

    def _start_session_monitoring(self):
        self._monitor_thread = threading.Thread(
            target=self._monitor_sessions, daemon=True
        )
        self._monitor_thread.start()

    def _monitor_sessions(self):
        while not self._stop_monitoring.is_set():
            try:
                self._scan_sessions()
                # Use a shorter timeout to make the loop more responsive
                if self._stop_monitoring.wait(1.0):
                    break
            except Exception as e:
                logger.error(f"Tmux monitoring error: {e}")
                break

    def _scan_sessions(self):
        result = run_command(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            timeout=10,
        )
        new_sessions = {}
        if result.returncode == 0 and isinstance(result.stdout, str):
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    new_sessions[line.strip()] = line.strip()

        new_hash = hash(frozenset(new_sessions.keys()))
        if new_hash == self._last_sessions_hash:
            return
        self._last_sessions_hash = new_hash
        self._sessions = new_sessions
        idle_add(self.emit, "sessions_changed")

    def _ensure_monitoring_started(self):
        """Start monitoring if not already started."""
        if not self._monitoring_started and self._is_tmux_available():
            self._monitoring_started = True
            # Scan sessions once before starting monitoring
            self._scan_sessions()
            self._start_session_monitoring()

    def refresh_sessions(self):
        self._ensure_monitoring_started()
        self._scan_sessions()

    def stop(self):
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._stop_monitoring.set()
            self._monitor_thread.join(timeout=2.0)
            if self._monitor_thread.is_alive():
                logger.warning("Tmux monitor thread did not stop gracefully")

    @Property(list, "readable")
    def session_names(self) -> list[str]:
        self._ensure_monitoring_started()
        return list(self._sessions.keys())

    @Property(int, "readable")
    def session_count(self) -> int:
        self._ensure_monitoring_started()
        return len(self._sessions)

    def list_sessions(self) -> dict:
        """List all tmux sessions with detailed info."""
        self._ensure_monitoring_started()
        try:
            result = run_command(
                [
                    "tmux",
                    "list-sessions",
                    "-F",
                    "#{session_name}:#{session_windows}:#{session_attached}:#{session_created_string}",
                ],
                timeout=5,
            )
            if result.returncode != 0:
                if "no server running" in (result.stderr or "").lower():
                    return {"success": True, "error": None, "data": []}
                return {
                    "success": False,
                    "error": result.stderr or "Unknown error",
                    "data": [],
                }

            sessions = []
            if isinstance(result.stdout, str):
                for line in result.stdout.strip().split("\n"):
                    if not line.strip():
                        continue
                    parts = line.split(":")
                    if len(parts) >= 4:
                        sessions.append(
                            {
                                "name": parts[0],
                                "windows": int(parts[1]) if parts[1].isdigit() else 0,
                                "attached": parts[2] == "1",
                                "created": parts[3],
                            }
                        )
            return {"success": True, "error": None, "data": sessions}
        except Exception as e:
            return {"success": False, "error": str(e), "data": []}

    def _expand_path(self, path: str) -> str:
        if not path:
            return str(Path.home())

        if not (path.startswith("/") or path.startswith("~")):
            path = f"~/{path}"

        expanded = os.path.expanduser(path)
        absolute = os.path.abspath(expanded)

        return absolute

    def new_session(
        self, session_name: str = None, terminal: str = "kitty", directory: str = None
    ) -> dict:
        self._ensure_monitoring_started()
        if not session_name:
            counter = 0
            while str(counter) in self._sessions:
                counter += 1
            session_name = str(counter)

        clean_name = session_name.strip().replace(" ", "_")
        if clean_name in self._sessions:
            return {
                "success": False,
                "error": f"Session '{clean_name}' already exists",
                "data": None,
            }

        working_dir = self._expand_path(directory)

        result = run_command(
            [
                "tmux",
                "new-session",
                "-d",
                "-s",
                clean_name,
                "-c",
                working_dir,
            ],
            timeout=10,
        )

        if result.returncode != 0:
            return {
                "success": False,
                "error": result.stderr or "Failed to create session",
                "data": None,
            }

        self._scan_sessions()
        self._open_in_terminal(clean_name, terminal, working_dir)
        return {"success": True, "error": None, "data": clean_name}

    def attach_session(
        self, session_name: str, terminal: str = "kitty", directory: str = None
    ) -> bool:
        self._ensure_monitoring_started()
        if session_name not in self._sessions:
            return False
        working_dir = self._expand_path(directory)
        return self._open_in_terminal(session_name, terminal, working_dir)

    def kill_session(self, session_name: str) -> dict:
        self._ensure_monitoring_started()
        if session_name not in self._sessions:
            return {
                "success": False,
                "error": f"Session '{session_name}' not found",
                "data": None,
            }

        result = run_command(["tmux", "kill-session", "-t", session_name], timeout=10)

        if result.returncode != 0:
            return {
                "success": False,
                "error": result.stderr or "Failed to kill session",
                "data": None,
            }

        self._scan_sessions()
        return {"success": True, "error": None, "data": None}

    def rename_session(self, old_name: str, new_name: str) -> dict:
        self._ensure_monitoring_started()
        if old_name not in self._sessions:
            return {
                "success": False,
                "error": f"Session '{old_name}' not found",
                "data": None,
            }
        if new_name in self._sessions:
            return {
                "success": False,
                "error": f"Session '{new_name}' already exists",
                "data": None,
            }

        result = run_command(
            ["tmux", "rename-session", "-t", old_name, new_name], timeout=10
        )

        if result.returncode != 0:
            return {
                "success": False,
                "error": result.stderr or "Failed to rename session",
                "data": None,
            }

        self._scan_sessions()
        return {"success": True, "error": None, "data": new_name}

    def _open_in_terminal(
        self, session_name: str, terminal: str, directory: str
    ) -> bool:
        cmd = terminal_open_in_directory_command(
            terminal,
            directory,
            title=f"tmux: {session_name}",
            inner_command=f"tmux attach-session -t {session_name}",
        )
        exec_shell_command_async(cmd)
        return True
