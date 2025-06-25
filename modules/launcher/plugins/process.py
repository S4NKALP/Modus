import time
import threading
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
            for proc in psutil.process_iter(['pid']):
                try:
                    pid = proc.info['pid']
                    # Initialize CPU monitoring - this establishes baseline for future readings
                    proc.cpu_percent()
                    self._cpu_cache[pid] = proc
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
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
        """Get fresh live process data with CPU/RAM information."""
        try:
            processes = []
            current_time = time.time()

            # Initialize CPU monitoring if this is the first call or enough time has passed
            if current_time - self._last_cpu_update > 0.1:  # Update every 100ms
                # Pre-populate CPU cache for all processes
                for proc in psutil.process_iter(['pid']):
                    try:
                        pid = proc.info['pid']
                        # Initialize CPU monitoring - this call establishes baseline
                        proc.cpu_percent()
                        self._cpu_cache[pid] = proc
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        continue
                self._last_cpu_update = current_time

            # Get process data with meaningful CPU readings
            for proc in psutil.process_iter(['pid', 'name', 'status']):
                try:
                    info = proc.info
                    if info['status'] == psutil.STATUS_ZOMBIE:
                        continue

                    pid = info['pid']

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
                    # psutil returns total CPU across all cores, so divide by core count
                    cpu_cores = psutil.cpu_count()
                    if cpu_cores and cpu_percent > 0:
                        cpu_percent = min(100.0, cpu_percent / cpu_cores)

                    memory_info = proc.memory_info()
                    memory_percent = proc.memory_percent()
                    memory_mb = memory_info.rss / (1024 * 1024) if memory_info else 0

                    process_data = {
                        'pid': pid,
                        'name': info['name'] or 'Unknown',
                        'cpu_percent': cpu_percent,
                        'memory_percent': memory_percent,
                        'memory_mb': memory_mb,
                        'status': info['status']
                    }
                    processes.append(process_data)

                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue

            # Clean up old entries from cache
            current_pids = {proc['pid'] for proc in processes}
            self._cpu_cache = {pid: proc for pid, proc in self._cpu_cache.items() if pid in current_pids}

            # Sort by combined CPU and memory usage for better display
            processes.sort(key=lambda x: (x['cpu_percent'] + x['memory_percent']), reverse=True)
            return processes

        except Exception as e:
            print(f"ProcessPlugin: Error getting process data: {e}")
            return []

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
                proc for proc in processes
                if query in proc['name'].lower() or query in str(proc['pid'])
            ]

        # Limit to top 20 processes to avoid overwhelming the UI
        for proc in filtered_processes[:20]:
            result = self._create_process_result(proc)
            if result:
                results.append(result)

        return results

    def _create_process_result(self, proc_data: dict) -> Result:
        """Create a Result object for a process."""
        try:
            pid = proc_data['pid']
            name = proc_data['name']
            cpu_percent = proc_data['cpu_percent']
            memory_percent = proc_data['memory_percent']
            memory_mb = proc_data['memory_mb']

            # Format the title and subtitle with live indicator
            title = f"{name} (PID: {pid})"

            # Add visual indicators for high usage
            cpu_indicator = "🔥" if cpu_percent > 80 else "⚡" if cpu_percent > 50 else ""
            mem_indicator = "💾" if memory_percent > 80 else ""

            subtitle = f"CPU: {cpu_percent:.1f}%{cpu_indicator} | Memory: {memory_mb:.1f}MB ({memory_percent:.1f}%){mem_indicator}"

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
                    "keep_launcher_open": True,  # Keep launcher open to see live updates
                    "alt_action": lambda p=pid: self._kill_process(p),
                },
            )
        except Exception as e:
            print(f"ProcessPlugin: Error creating process result: {e}")
            return None



    def _kill_process(self, pid: int):
        """Kill a process by PID."""
        try:
            proc = psutil.Process(pid)
            proc_name = proc.name()

            # Try graceful termination first
            proc.terminate()

            # Wait a bit for graceful termination
            try:
                proc.wait(timeout=3)
                print(f"✓ Successfully terminated process '{proc_name}' (PID: {pid})")
            except psutil.TimeoutExpired:
                # Force kill if graceful termination failed
                proc.kill()
                print(f"✓ Force killed process '{proc_name}' (PID: {pid})")



        except psutil.NoSuchProcess:
            print(f"✗ Process {pid} not found - may have already been terminated")
        except psutil.AccessDenied:
            print(f"✗ Access denied - cannot kill process {pid} (insufficient permissions)")
        except Exception as e:
            print(f"✗ Error killing process {pid}: {e}")

    def _start_refresh_thread(self):
        """Start background thread for auto-refreshing process data in milliseconds."""

        def refresh_loop():
            while not self.stop_refresh.wait(0.5):  # Check every 500ms for real-time updates
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
                    process_dict = {proc['pid']: proc for proc in current_processes}

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
            cpu_percent = proc_data['cpu_percent']
            memory_percent = proc_data['memory_percent']
            memory_mb = proc_data['memory_mb']

            # CPU is already normalized in _get_live_process_data, so no need to normalize again

            # Update the subtitle with live data
            cpu_indicator = "🔥" if cpu_percent > 80 else "⚡" if cpu_percent > 50 else ""
            mem_indicator = "💾" if memory_percent > 80 else ""
            new_subtitle = f"CPU: {cpu_percent:.1f}%{cpu_indicator} | Memory: {memory_mb:.1f}MB ({memory_percent:.1f}%){mem_indicator}"

            # Find and update the subtitle label widget
            self._find_and_update_subtitle_label(result_item, new_subtitle)

            # Update the result data for consistency
            result_item.result.data.update({
                "cpu_percent": cpu_percent,
                "memory_percent": memory_percent,
                "memory_mb": memory_mb,
            })

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
