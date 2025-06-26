import threading
import time
from typing import List

import psutil

import utils.icons as icons
from modules.launcher.plugin_base import PluginBase
from modules.launcher.result import Result


class ProcessPlugin(PluginBase):
    """
    Plugin for viewing and managing running processes with live CPU/RAM updates.
    """

    def __init__(self):
        super().__init__()
        self.display_name = "Process Manager"
        self.description = "View and manage running processes"

        # Threading for auto-refresh
        self.refresh_thread = None
        self.stop_refresh = threading.Event()
        self.last_update = 0

        # CPU monitoring cache to get meaningful readings
        self._cpu_cache = {}
        self._last_cpu_update = 0

    def initialize(self):
        """Initialize the process plugin."""
        self.set_triggers(["ps"])
        # Pre-populate CPU cache for immediate meaningful readings
        self._initialize_cpu_monitoring()
        self._start_refresh_thread()

    def _initialize_cpu_monitoring(self):
        """Initialize CPU monitoring for all processes to get meaningful readings immediately."""
        try:
            for proc in psutil.process_iter(["pid"]):
                try:
                    pid = proc.info["pid"]
                    # Initialize CPU monitoring - this establishes baseline for future readings
                    proc.cpu_percent()
                    self._cpu_cache[pid] = proc
                except (
                    psutil.NoSuchProcess,
                    psutil.AccessDenied,
                    psutil.ZombieProcess,
                ):
                    continue
            self._last_cpu_update = time.time()
        except Exception as e:
            print(f"ProcessPlugin: Error initializing CPU monitoring: {e}")

    def cleanup(self):
        """Cleanup the process plugin."""
        self.stop_refresh.set()
        if self.refresh_thread:
            self.refresh_thread.join(timeout=1)
        # Clear CPU cache
        self._cpu_cache.clear()

    def _get_live_process_data(self):
        """Get fresh live process data with CPU/RAM information, grouped by application."""
        try:
            current_time = time.time()

            # Initialize CPU monitoring if this is the first call or enough time has passed
            if current_time - self._last_cpu_update > 0.1:  # Update every 100ms
                # Pre-populate CPU cache for all processes
                for proc in psutil.process_iter(["pid"]):
                    try:
                        pid = proc.info["pid"]
                        # Initialize CPU monitoring - this call establishes baseline
                        proc.cpu_percent()
                        self._cpu_cache[pid] = proc
                    except (
                        psutil.NoSuchProcess,
                        psutil.AccessDenied,
                        psutil.ZombieProcess,
                    ):
                        continue
                self._last_cpu_update = current_time

            # Group processes by application name
            app_groups = {}

            for proc in psutil.process_iter(["pid", "name", "status", "ppid"]):
                try:
                    info = proc.info
                    if info["status"] == psutil.STATUS_ZOMBIE:
                        continue

                    pid = info["pid"]
                    name = info["name"] or "Unknown"

                    # Get CPU percentage - use cached process if available for better readings
                    if pid in self._cpu_cache:
                        try:
                            cpu_percent = self._cpu_cache[pid].cpu_percent()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            cpu_percent = proc.cpu_percent()
                            self._cpu_cache[pid] = proc
                    else:
                        cpu_percent = proc.cpu_percent()
                        self._cpu_cache[pid] = proc

                    # Normalize CPU to 0-100% range (divide by number of cores)
                    cpu_cores = psutil.cpu_count()
                    if cpu_cores and cpu_percent > 0:
                        cpu_percent = min(100.0, cpu_percent / cpu_cores)

                    memory_info = proc.memory_info()
                    memory_percent = proc.memory_percent()
                    memory_mb = memory_info.rss / (1024 * 1024) if memory_info else 0

                    process_data = {
                        "pid": pid,
                        "ppid": info["ppid"],
                        "name": name,
                        "cpu_percent": cpu_percent,
                        "memory_percent": memory_percent,
                        "memory_mb": memory_mb,
                        "status": info["status"],
                    }

                    # Group processes by application name
                    app_name = self._get_app_name(name)
                    if app_name not in app_groups:
                        app_groups[app_name] = []
                    app_groups[app_name].append(process_data)

                except (
                    psutil.NoSuchProcess,
                    psutil.AccessDenied,
                    psutil.ZombieProcess,
                ):
                    continue

            # Create grouped results
            grouped_processes = []
            for app_name, app_processes in app_groups.items():
                if len(app_processes) == 1:
                    # Single process - show as individual
                    proc = app_processes[0]
                    proc["process_count"] = 1
                    grouped_processes.append(proc)
                else:
                    # Multiple processes - group them and sum resources
                    total_cpu = sum(p["cpu_percent"] for p in app_processes)
                    total_memory_mb = sum(p["memory_mb"] for p in app_processes)
                    total_memory_percent = sum(
                        p["memory_percent"] for p in app_processes
                    )

                    # Find the main process (usually the one with lowest PID)
                    main_process = min(app_processes, key=lambda x: x["pid"])

                    grouped_process = {
                        # Use main process PID for killing
                        "pid": main_process["pid"],
                        "name": app_name,
                        "cpu_percent": total_cpu,
                        "memory_percent": total_memory_percent,
                        "memory_mb": total_memory_mb,
                        "status": main_process["status"],
                        "process_count": len(app_processes),
                        "child_pids": [p["pid"] for p in app_processes],
                    }
                    grouped_processes.append(grouped_process)

            # Clean up old entries from cache
            all_pids = set()
            for app_processes in app_groups.values():
                all_pids.update(p["pid"] for p in app_processes)
            self._cpu_cache = {
                pid: proc for pid, proc in self._cpu_cache.items() if pid in all_pids
            }

            # Sort by combined CPU and memory usage for better display
            grouped_processes.sort(
                key=lambda x: (x["cpu_percent"] + x["memory_percent"]), reverse=True
            )
            return grouped_processes

        except Exception as e:
            print(f"ProcessPlugin: Error getting process data: {e}")
            return []

    def _get_app_name(self, process_name: str) -> str:
        """Extract application name from process name, handling common patterns."""
        # Remove common suffixes and normalize
        name = process_name.lower()

        # Handle common browser patterns
        if "firefox" in name:
            return "Firefox"
        elif "chrome" in name or "chromium" in name:
            return "Chrome"
        elif "zen" in name or name in [
            "socket process",
            "privileged cont",
            "rdd process",
            "isolated web co",
            "web content",
            "webextensions",
            "utility process",
            "isolated servic",
        ]:
            return "Zen Browser"
        elif "code" in name and ("helper" in name or "oss" in name or name == "code"):
            return "VS Code"
        elif name.startswith("python") and len(name) > 6:
            return "Python"
        elif name.startswith("node") and len(name) > 4:
            return "Node.js"
        elif "electron" in name:
            return "Electron"
        elif "java" in name:
            return "Java"
        elif "gnome" in name:
            return "GNOME"
        elif "gtk" in name:
            return "GTK App"

        # Remove common suffixes
        suffixes = [
            "-bin",
            "-real",
            "-wrapped",
            ".bin",
            ".exe",
            "-helper",
            "-gpu",
            "-renderer",
        ]
        for suffix in suffixes:
            if name.endswith(suffix):
                name = name[: -len(suffix)]
                break

        # Capitalize first letter
        return name.capitalize()

    def query(self, query_string: str) -> List[Result]:
        """Search for processes matching the query with live updates - ALWAYS FRESH DATA."""
        # ALWAYS get completely fresh data - NO CACHING EVER
        processes = self._get_live_process_data()

        query = query_string.strip().lower()
        results = []

        # Filter processes based on query
        filtered_processes = processes
        if query:
            filtered_processes = [
                proc
                for proc in processes
                if query in proc["name"].lower() or query in str(proc["pid"])
            ]

        # Limit to top 20 processes to avoid overwhelming the UI
        for proc in filtered_processes[:20]:
            result = self._create_process_result(proc)
            if result:
                results.append(result)

        return results

    def _create_process_result(self, proc_data: dict) -> Result:
        """Create a Result object for a process or grouped application."""
        try:
            pid = proc_data["pid"]
            name = proc_data["name"]
            cpu_percent = proc_data["cpu_percent"]
            memory_percent = proc_data["memory_percent"]
            memory_mb = proc_data["memory_mb"]
            process_count = proc_data.get("process_count", 1)

            # Format the title with process count if grouped
            if process_count > 1:
                title = f"{name} ({process_count} processes)"
            else:
                title = f"{name} (PID: {pid})"

            # Add visual indicators for high usage
            cpu_indicator = (
                "🔥" if cpu_percent > 80 else "⚡" if cpu_percent > 50 else ""
            )
            mem_indicator = "💾" if memory_percent > 80 else ""

            subtitle = f"CPU: {cpu_percent:.1f}%{cpu_indicator} | Memory: {
                memory_mb:.1f
            }MB ({memory_percent:.1f}%){mem_indicator}"

            # Choose icon based on CPU usage
            if cpu_percent > 50:
                icon_markup = icons.cpu
            elif memory_percent > 50:
                icon_markup = icons.memory
            else:
                icon_markup = icons.terminal

            return Result(
                title=title,
                subtitle=subtitle,
                icon_markup=icon_markup,
                action=lambda: None,  # No action on Enter - just show process info
                relevance=min(1.0, (cpu_percent + memory_percent) / 100.0),
                plugin_name=self.display_name,
                data={
                    "type": "process",
                    "pid": pid,
                    "name": name,
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory_percent,
                    "memory_mb": memory_mb,
                    "process_count": process_count,
                    "child_pids": proc_data.get("child_pids", [pid]),
                    "keep_launcher_open": True,  # Keep launcher open to see live updates
                    "alt_action": lambda data=proc_data: self._kill_process_group(data),
                },
            )
        except Exception as e:
            print(f"ProcessPlugin: Error creating process result: {e}")
            return None

    def _kill_process_group(self, proc_data: dict):
        """Kill a process group (application with all its subprocesses)."""
        try:
            process_count = proc_data.get("process_count", 1)
            child_pids = proc_data.get("child_pids", [proc_data["pid"]])
            app_name = proc_data["name"]

            if process_count == 1:
                # Single process
                self._kill_process(proc_data["pid"])
            else:
                # Multiple processes - kill all
                killed_count = 0
                for pid in child_pids:
                    if self._kill_process(pid, silent=True):
                        killed_count += 1

                print(
                    f"✓ Terminated {killed_count}/{len(child_pids)} processes for '{
                        app_name
                    }'"
                )

        except Exception as e:
            print(f"✗ Error killing process group: {e}")

    def _kill_process(self, pid: int, silent: bool = False) -> bool:
        """Kill a process by PID. Returns True if successful."""
        try:
            proc = psutil.Process(pid)
            proc_name = proc.name()

            # Try graceful termination first
            proc.terminate()

            # Wait a bit for graceful termination
            try:
                proc.wait(timeout=3)
                if not silent:
                    print(
                        f"✓ Successfully terminated process '{proc_name}' (PID: {pid})"
                    )
                return True
            except psutil.TimeoutExpired:
                # Force kill if graceful termination failed
                proc.kill()
                if not silent:
                    print(f"✓ Force killed process '{proc_name}' (PID: {pid})")
                return True

        except psutil.NoSuchProcess:
            if not silent:
                print(f"✗ Process {pid} not found - may have already been terminated")
            return False
        except psutil.AccessDenied:
            if not silent:
                print(
                    f"✗ Access denied - cannot kill process {pid} (insufficient permissions)"
                )
            return False
        except Exception as e:
            if not silent:
                print(f"✗ Error killing process {pid}: {e}")
            return False

    def _start_refresh_thread(self):
        """Start background thread for auto-refreshing process data in milliseconds."""

        def refresh_loop():
            # Check every 500ms for real-time updates
            while not self.stop_refresh.wait(0.5):
                current_time = time.time()
                if current_time - self.last_update >= 0.5:  # Update every 500ms
                    self.last_update = current_time
                    # Update existing process labels without full refresh
                    try:
                        self._selective_force_refresh()
                    except Exception:
                        pass

        self.refresh_thread = threading.Thread(target=refresh_loop, daemon=True)
        self.refresh_thread.start()

    def _selective_force_refresh(self):
        """Update process data in existing result items (like OTP plugin)."""
        try:
            import gc

            from gi.repository import GLib

            def do_update():
                try:
                    for obj in gc.get_objects():
                        if (
                            hasattr(obj, "__class__")
                            and obj.__class__.__name__ == "Launcher"
                            and hasattr(obj, "results_box")
                            and hasattr(obj, "visible")
                            and obj.visible
                            and hasattr(obj, "results")
                            and obj.results
                        ):
                            has_process_results = any(
                                result.data and result.data.get("type") == "process"
                                for result in obj.results
                                if hasattr(result, "data") and result.data
                            )

                            if has_process_results:
                                self._update_existing_process_labels(obj.results_box)
                                return False
                except Exception:
                    pass
                return False

            GLib.idle_add(do_update)
        except Exception:
            pass

    def _update_existing_process_labels(self, results_box):
        """Update subtitle labels in existing ResultItem widgets with FRESH data (optimized)."""
        try:
            # Get fresh process data in background thread - optimized
            def get_data_async():
                return self._get_live_process_data()

            # Run data collection in background to avoid blocking UI
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(get_data_async)
                try:
                    current_processes = future.result(timeout=1.0)  # 1 second timeout
                    process_dict = {proc["pid"]: proc for proc in current_processes}

                    for child in results_box.get_children():
                        if (
                            hasattr(child, "__class__")
                            and child.__class__.__name__ == "ResultItem"
                            and hasattr(child, "result")
                            and hasattr(child.result, "data")
                            and child.result.data
                            and child.result.data.get("type") == "process"
                        ):
                            self._update_process_result_item(child, process_dict)
                except concurrent.futures.TimeoutError:
                    # Skip update if it takes too long
                    pass
        except Exception as e:
            print(f"Error updating process labels: {e}")

    def _update_process_result_item(self, result_item, process_dict):
        """Update both the title and subtitle of a specific process ResultItem."""
        try:
            pid = result_item.result.data.get("pid")
            if not pid or pid not in process_dict:
                return

            proc_data = process_dict[pid]
            cpu_percent = proc_data["cpu_percent"]
            memory_percent = proc_data["memory_percent"]
            memory_mb = proc_data["memory_mb"]

            # CPU is already normalized in _get_live_process_data, so no need to normalize again

            # Update the subtitle with live data
            cpu_indicator = (
                "🔥" if cpu_percent > 80 else "⚡" if cpu_percent > 50 else ""
            )
            mem_indicator = "💾" if memory_percent > 80 else ""
            new_subtitle = f"CPU: {cpu_percent:.1f}%{cpu_indicator} | Memory: {
                memory_mb:.1f
            }MB ({memory_percent:.1f}%){mem_indicator}"

            # Find and update the subtitle label widget
            self._find_and_update_subtitle_label(result_item, new_subtitle)

            # Update the result data for consistency
            result_item.result.data.update(
                {
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory_percent,
                    "memory_mb": memory_mb,
                }
            )

        except Exception as e:
            print(f"Error updating process result item: {e}")

    def _find_and_update_subtitle_label(self, result_item, new_subtitle):
        """Find the subtitle label widget and update its text."""

        def find_subtitle_label(widget):
            if (
                hasattr(widget, "get_name")
                and widget.get_name() == "result-item-subtitle"
            ):
                return widget
            if hasattr(widget, "get_children"):
                for child in widget.get_children():
                    found = find_subtitle_label(child)
                    if found:
                        return found
            return None

        subtitle_label = find_subtitle_label(result_item)
        if subtitle_label and hasattr(subtitle_label, "set_text"):
            subtitle_label.set_text(new_subtitle)
