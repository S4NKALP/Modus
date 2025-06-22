"""
Pomodoro plugin for the launcher.
Implements the Pomodoro Technique timer with work/break cycles.
"""

import threading
import time
import subprocess
from typing import List
from modules.launcher.plugin_base import PluginBase
from modules.launcher.result import Result
import utils.icons as icons
from gi.repository import GLib


class PomodoroTimer:
    """
    Core Pomodoro timer implementation.
    """

    def __init__(self):
        self.is_break = True
        self.timer = None
        self.countdown_timers = []  # Store countdown timer references
        self.remaining_till_long_break = 0
        self.end_time = 0
        self.pomodoro_duration = 0
        self.break_duration = 0
        self.long_break_duration = 0
        self.count = 0
        self.current_cycle = 0
        self.total_cycles_completed = 0
        self._cached_status = "Inactive"
        self._last_status_update = 0

    def _send_notification_async(self, title, message):
        """Send a desktop notification asynchronously."""
        def send_notification():
            try:
                subprocess.run(
                    ["notify-send", "-a", "Pomodoro Timer", "-i", "timer", title, message],
                    check=False,
                )
            except Exception as e:
                print(f"Failed to send notification: {e}")

        # Run in background thread to avoid blocking UI
        thread = threading.Thread(target=send_notification, daemon=True)
        thread.start()

    def _send_countdown_notification_async(self, seconds_left):
        """Send countdown notification asynchronously."""
        def send_countdown():
            try:
                subprocess.run(
                    [
                        "notify-send",
                        "-a",
                        "Pomodoro Timer",
                        "-i",
                        "timer",
                        "-t",
                        "1000",  # Show for 1 second
                        "⏰ Pomodoro Timer",
                        f"Time's up in {seconds_left} seconds!",
                    ],
                    check=False,
                )
            except Exception as e:
                print(f"Failed to send countdown notification: {e}")

        # Run in background thread to avoid blocking UI
        thread = threading.Thread(target=send_countdown, daemon=True)
        thread.start()

    def _schedule_countdown_notifications(self, duration_seconds):
        """Schedule countdown notifications for the last 3 seconds."""
        # Clear any existing countdown timers
        self._clear_countdown_timers()

        if duration_seconds > 3:
            # Schedule countdown notifications for 3, 2, 1 seconds before end
            for countdown in [3, 2, 1]:
                delay = duration_seconds - countdown
                if delay > 0:
                    timer = threading.Timer(
                        delay, self._send_countdown_notification_async, [countdown]
                    )
                    self.countdown_timers.append(timer)
                    timer.start()

    def _clear_countdown_timers(self):
        """Clear all countdown timers."""
        for timer in self.countdown_timers:
            if timer.is_alive():
                timer.cancel()
        self.countdown_timers.clear()

    def timeout(self):
        """Handle timer timeout and switch between work/break periods."""
        if self.is_break:
            # Starting work period
            duration = self.pomodoro_duration * 60
            self.timer = threading.Timer(duration, self.timeout)
            self.end_time = time.time() + duration
            self.current_cycle += 1

            # Send notification for work period start
            self._send_notification_async(
                "🍅 Work Time!",
                f"Starting work period {self.current_cycle} ({
                    self.pomodoro_duration
                } minutes)",
            )

            # Schedule countdown notifications
            self._schedule_countdown_notifications(duration)

            self.timer.start()
        else:
            # Starting break period
            self.remaining_till_long_break -= 1
            self.total_cycles_completed += 1

            if self.remaining_till_long_break == 0:
                self.remaining_till_long_break = self.count
                duration = self.long_break_duration * 60

                # Send notification for long break
                self._send_notification_async(
                    "🌟 Long Break Time!",
                    f"Take a long break ({
                        self.long_break_duration
                    } minutes)\nYou've completed {self.count} cycles! Total: {
                        self.total_cycles_completed
                    }",
                )

            else:
                duration = self.break_duration * 60

                # Send notification for short break
                self._send_notification_async(
                    "☕ Break Time!",
                    f"Take a short break ({self.break_duration} minutes)\nCycle {
                        self.current_cycle
                    } completed! Total: {self.total_cycles_completed}",
                )

            # Schedule countdown notifications for break end
            self._schedule_countdown_notifications(duration)

            self.end_time = time.time() + duration
            self.timer = threading.Timer(duration, self.timeout)
            self.timer.start()

        self.is_break = not self.is_break
        # Update cached status after state change
        self._update_cached_status()

    def start(self, pomodoro_duration, break_duration, long_break_duration, count):
        """Start the Pomodoro timer with specified durations."""
        self.stop()
        self.pomodoro_duration = pomodoro_duration
        self.break_duration = break_duration
        self.long_break_duration = long_break_duration
        self.count = count
        self.remaining_till_long_break = count
        self.current_cycle = 0
        self.total_cycles_completed = 0
        self.is_break = True

        # Send initial notification
        self._send_notification_async(
            "🍅 Pomodoro Started!",
            f"Timer started: {pomodoro_duration}min work, {break_duration}min break\n{
                count
            } cycles with {long_break_duration}min long breaks",
        )

        self.timeout()

    def stop(self):
        """Stop the Pomodoro timer."""
        if self.is_active():
            self.timer.cancel()
            self.timer = None

            # Clear countdown timers
            self._clear_countdown_timers()

            # Send stop notification
            self._send_notification_async(
                "⏹️ Pomodoro Stopped",
                f"Timer stopped after {
                    self.total_cycles_completed
                } completed cycles\nCurrent work period: {self.current_cycle}",
            )

            # Update cached status
            self._cached_status = "Inactive"

    def is_active(self):
        """Check if the timer is currently active."""
        return self.timer is not None

    def _update_cached_status(self):
        """Update the cached status string."""
        current_time = time.time()

        if not self.is_active():
            self._cached_status = "Inactive"
            return

        remaining_seconds = max(0, int(self.end_time - current_time))
        remaining_minutes = remaining_seconds // 60
        remaining_seconds = remaining_seconds % 60

        if self.is_break:
            if self.remaining_till_long_break == self.count:
                period_type = "Long Break"
            else:
                period_type = "Short Break"
        else:
            period_type = f"Work (Cycle {self.current_cycle})"

        self._cached_status = f"{period_type} - {remaining_minutes:02d}:{remaining_seconds:02d} | Total: {self.total_cycles_completed}"
        self._last_status_update = current_time

    def get_status(self):
        """Get current timer status with caching."""
        current_time = time.time()

        # Update cache if it's been more than 1 second or timer is inactive
        if (current_time - self._last_status_update > 1.0) or not self.is_active():
            self._update_cached_status()

        return self._cached_status


class PomodoroPlugin(PluginBase):
    """
    Pomodoro Technique plugin for the launcher.
    """

    # Default settings
    DEFAULT_POMODORO_DURATION = 25
    DEFAULT_BREAK_DURATION = 5
    DEFAULT_LONG_BREAK_DURATION = 15
    DEFAULT_POMODORO_COUNT = 4

    def __init__(self):
        super().__init__()
        self.display_name = "Pomodoro"
        self.description = "Pomodoro Technique timer for productivity"
        self.pomodoro = PomodoroTimer()

    def initialize(self):
        """Initialize the Pomodoro plugin."""
        self.set_triggers(["pomo", "pomo "])

    def cleanup(self):
        """Cleanup the Pomodoro plugin."""
        self.pomodoro.stop()

    def _force_refresh(self):
        """Force refresh the launcher to update the display."""
        try:
            def trigger_refresh():
                try:
                    # Fallback: try to find launcher instance through other means
                    import gc

                    for obj in gc.get_objects():
                        if (
                            hasattr(obj, "__class__")
                            and obj.__class__.__name__ == "Launcher"
                        ):
                            if hasattr(obj, "search_entry") and hasattr(
                                obj, "_perform_search"
                            ):
                                obj.search_entry.set_text("pomo ")
                                obj.search_entry.set_position(-1)
                                obj._perform_search("pomo ")
                                return False

                except Exception as e:
                    print(f"Error forcing launcher refresh: {e}")

                return False  # Don't repeat

            # Use a small delay to ensure the action completes first
            GLib.timeout_add(50, trigger_refresh)

        except Exception as e:
            print(f"Could not trigger refresh: {e}")

    def query(self, query_string: str) -> List[Result]:
        """Process Pomodoro queries."""
        results = []

        if self.pomodoro.is_active():
            # Timer is running - show status and stop option
            status = self.pomodoro.get_status()

            # Show current status
            results.append(
                Result(
                    title="Pomodoro Timer Active",
                    subtitle=status,
                    icon_markup=icons.timer_on,
                    action=lambda: None,  # No action, just status display
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={"type": "status"},
                )
            )

            # Show stop option with refresh
            def stop_and_refresh():
                self.pomodoro.stop()
                self._force_refresh()

            results.append(
                Result(
                    title="Stop Pomodoro",
                    subtitle="Stop the current timer",
                    icon_markup=icons.timer_off,
                    action=stop_and_refresh,
                    relevance=0.9,
                    plugin_name=self.display_name,
                    data={"type": "stop"},
                )
            )
        else:
            # Timer is not running - show start options
            if not query_string.strip():
                # No parameters - show default start option
                def start_default_and_refresh():
                    self.pomodoro.start(
                        self.DEFAULT_POMODORO_DURATION,
                        self.DEFAULT_BREAK_DURATION,
                        self.DEFAULT_LONG_BREAK_DURATION,
                        self.DEFAULT_POMODORO_COUNT,
                    )
                    self._force_refresh()

                results.append(
                    Result(
                        title="Start Pomodoro",
                        subtitle=f"{self.DEFAULT_POMODORO_DURATION} min work, {
                            self.DEFAULT_BREAK_DURATION
                        } min break, {
                            self.DEFAULT_LONG_BREAK_DURATION
                        } min long break, {self.DEFAULT_POMODORO_COUNT} cycles",
                        icon_markup=icons.timer_on,
                        action=start_default_and_refresh,
                        relevance=1.0,
                        plugin_name=self.display_name,
                        data={"type": "start_default"},
                    )
                )
            else:
                # Parse parameters
                tokens = query_string.strip().split()

                # Validate parameters
                if len(tokens) > 4 or not all(t.isdigit() for t in tokens):
                    results.append(
                        Result(
                            title="Invalid Parameters",
                            subtitle="Usage: [work_minutes] [break_minutes] [long_break_minutes] [cycle_count]",
                            icon_markup=icons.alert,
                            action=lambda: None,
                            relevance=0.5,
                            plugin_name=self.display_name,
                            data={"type": "error"},
                        )
                    )
                else:
                    # Parse valid parameters
                    p = (
                        int(tokens[0])
                        if len(tokens) > 0
                        else self.DEFAULT_POMODORO_DURATION
                    )
                    b = (
                        int(tokens[1])
                        if len(tokens) > 1
                        else self.DEFAULT_BREAK_DURATION
                    )
                    lb = (
                        int(tokens[2])
                        if len(tokens) > 2
                        else self.DEFAULT_LONG_BREAK_DURATION
                    )
                    c = (
                        int(tokens[3])
                        if len(tokens) > 3
                        else self.DEFAULT_POMODORO_COUNT
                    )

                    def start_custom_and_refresh(_p=p, _b=b, _lb=lb, _c=c):
                        self.pomodoro.start(_p, _b, _lb, _c)
                        self._force_refresh()

                    results.append(
                        Result(
                            title="Start Pomodoro",
                            subtitle=f"{p} min work, {b} min break, {
                                lb
                            } min long break, {c} cycles",
                            icon_markup=icons.timer_on,
                            action=start_custom_and_refresh,
                            relevance=1.0,
                            plugin_name=self.display_name,
                            data={"type": "start_custom", "params": [p, b, lb, c]},
                        )
                    )

        return results
