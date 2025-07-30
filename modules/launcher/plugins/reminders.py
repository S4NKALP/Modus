import re
import subprocess
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import utils.icons as icons
from modules.launcher.plugin_base import PluginBase
from modules.launcher.result import Result


class Reminder:
    """
    Represents a single reminder with its timer and metadata.
    """

    def __init__(
        self,
        reminder_id: int,
        message: str,
        target_time: datetime,
        timer: threading.Timer,
    ):
        self.id = reminder_id
        self.message = message
        self.target_time = target_time
        self.timer = timer
        self.created_time = datetime.now()

    def cancel(self):
        """Cancel this reminder."""
        if self.timer:
            self.timer.cancel()

    def get_time_remaining(self) -> str:
        """Get formatted time remaining until reminder."""
        now = datetime.now()
        if self.target_time <= now:
            return "Overdue"

        delta = self.target_time - now
        total_seconds = int(delta.total_seconds())

        if total_seconds < 60:
            return f"{total_seconds}s"
        elif total_seconds < 3600:
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            return f"{minutes}m {seconds}s" if seconds > 0 else f"{minutes}m"
        else:
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            return f"{hours}h {minutes}m" if minutes > 0 else f"{hours}h"

    def get_target_time_str(self) -> str:
        """Get formatted target time."""
        return self.target_time.strftime("%H:%M")


class RemindersPlugin(PluginBase):
    """
    Time-based reminders plugin for the launcher.
    """

    def __init__(self):
        super().__init__()
        self.display_name = "Reminders"
        self.description = "Set time-based reminders with notifications"
        self.reminders: Dict[int, Reminder] = {}
        self.next_id = 1

        # Regex patterns for time parsing
        self.time_patterns = {
            "relative_time": re.compile(r"^(\d+)([smhd])$"),  # 5m, 30s, 2h, 1d
            "absolute_time": re.compile(r"^(\d{1,2}):(\d{2})$"),  # 14:30, 9:15
            "relative_with_unit": re.compile(
                r"^(\d+)\s*(min|mins|minute|minutes|hour|hours|sec|seconds|day|days)$",
                re.IGNORECASE,
            ),
        }

    def initialize(self):
        """Initialize the reminders plugin."""
        self.set_triggers(["remind"])

    def cleanup(self):
        """Cleanup the reminders plugin."""
        # Cancel all active reminders
        for reminder in self.reminders.values():
            reminder.cancel()
        self.reminders.clear()

    def _send_notification(self, title: str, message: str):
        """Send a desktop notification using notify-send."""
        try:
            subprocess.run(
                ["notify-send", "-a", "Reminders", "-i", "alarm-clock", title, message],
                check=False,
            )
        except Exception as e:
            print(f"Failed to send notification: {e}")

    def _parse_time_input(self, time_str: str) -> Optional[datetime]:
        """
        Parse various time input formats and return target datetime.

        Supported formats:
        - 5m, 30s, 2h, 1d (relative time)
        - 14:30, 9:15 (absolute time today)
        - 5 minutes, 2 hours (relative with full unit names)
        """
        time_str = time_str.strip().lower()

        # Try relative time format (5m, 30s, 2h, 1d)
        match = self.time_patterns["relative_time"].match(time_str)
        if match:
            value, unit = match.groups()
            value = int(value)

            if unit == "s":
                delta = timedelta(seconds=value)
            elif unit == "m":
                delta = timedelta(minutes=value)
            elif unit == "h":
                delta = timedelta(hours=value)
            elif unit == "d":
                delta = timedelta(days=value)
            else:
                return None

            return datetime.now() + delta

        # Try absolute time format (14:30, 9:15)
        match = self.time_patterns["absolute_time"].match(time_str)
        if match:
            hour, minute = map(int, match.groups())
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                target = datetime.now().replace(
                    hour=hour, minute=minute, second=0, microsecond=0
                )
                # If the time has already passed today, schedule for tomorrow
                if target <= datetime.now():
                    target += timedelta(days=1)
                return target

        # Try relative time with full unit names
        match = self.time_patterns["relative_with_unit"].match(time_str)
        if match:
            value, unit = match.groups()
            value = int(value)
            unit = unit.lower()

            if unit in ["sec", "seconds"]:
                delta = timedelta(seconds=value)
            elif unit in ["min", "mins", "minute", "minutes"]:
                delta = timedelta(minutes=value)
            elif unit in ["hour", "hours"]:
                delta = timedelta(hours=value)
            elif unit in ["day", "days"]:
                delta = timedelta(days=value)
            else:
                return None

            return datetime.now() + delta

        return None

    def _create_reminder(self, time_str: str, message: str) -> Optional[Reminder]:
        """Create a new reminder with the given time and message."""
        target_time = self._parse_time_input(time_str)
        if not target_time:
            return None

        # Calculate delay in seconds
        delay = (target_time - datetime.now()).total_seconds()
        if delay <= 0:
            return None

        # Create timer that will trigger the notification
        timer = threading.Timer(delay, self._trigger_reminder, [self.next_id, message])

        # Create reminder object
        reminder = Reminder(self.next_id, message, target_time, timer)

        # Store reminder and start timer
        self.reminders[self.next_id] = reminder
        timer.start()

        # Increment ID for next reminder
        self.next_id += 1

        return reminder

    def _trigger_reminder(self, reminder_id: int, message: str):
        """Trigger a reminder notification and remove it from active reminders."""
        # Send notification
        self._send_notification("⏰ Reminder", message)

        # Remove from active reminders
        if reminder_id in self.reminders:
            del self.reminders[reminder_id]

    def _cancel_reminder(self, reminder_id: Optional[int] = None) -> int:
        """Cancel a specific reminder or all reminders. Returns number of cancelled reminders."""
        if reminder_id is not None:
            if reminder_id in self.reminders:
                self.reminders[reminder_id].cancel()
                del self.reminders[reminder_id]
                return 1
            return 0
        else:
            # Cancel all reminders
            count = len(self.reminders)
            for reminder in self.reminders.values():
                reminder.cancel()
            self.reminders.clear()
            return count

    def _format_time_remaining(self, total_seconds: float) -> str:
        """Format time remaining in a human-readable way."""
        total_seconds = int(total_seconds)

        if total_seconds < 60:
            return f"{total_seconds}s"
        elif total_seconds < 3600:
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            return f"{minutes}m {seconds}s" if seconds > 0 else f"{minutes}m"
        else:
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            return f"{hours}h {minutes}m" if minutes > 0 else f"{hours}h"

    def _create_and_confirm_reminder(self, time_str: str, message: str):
        """Actually create the reminder when the user presses Enter."""
        reminder = self._create_reminder(time_str, message)
        if reminder:
            time_remaining = reminder.get_time_remaining()
            self._send_notification(
                "✅ Reminder Created", f"Reminder set for {time_remaining}: {message}"
            )
        else:
            self._send_notification(
                "❌ Failed to Create Reminder", "The specified time may be in the past"
            )

    def query(self, query_string: str) -> List[Result]:
        """Process reminder queries."""
        results = []
        query = query_string.strip()

        if not query:
            # Show help and active reminders count
            active_count = len(self.reminders)
            results.append(
                Result(
                    title="Reminders Help",
                    subtitle=f"Active reminders: {
                        active_count
                    } | Usage: remind 5m Take a break",
                    icon_markup=icons.timer_on,
                    action=lambda: None,
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={"type": "help"},
                )
            )

            # Show quick examples
            examples = [
                ("remind 5m Take a break", "Set 5 minute reminder"),
                ("remind 14:30 Meeting", "Set reminder for 2:30 PM"),
                ("remind list", "List active reminders"),
                ("remind cancel", "Cancel all reminders"),
            ]

            for example, desc in examples:
                results.append(
                    Result(
                        title=example,
                        subtitle=desc,
                        icon_markup=icons.timer_on,
                        action=lambda: None,
                        relevance=0.8,
                        plugin_name=self.display_name,
                        data={"type": "example"},
                    )
                )

            return results

        # Handle list command
        if query.lower() in ["list", "ls", "show"]:
            if not self.reminders:
                results.append(
                    Result(
                        title="No Active Reminders",
                        subtitle="Use 'remind 5m message' to set a reminder",
                        icon_markup=icons.timer_off,
                        action=lambda: None,
                        relevance=1.0,
                        plugin_name=self.display_name,
                        data={"type": "empty_list"},
                    )
                )
            else:
                for reminder in sorted(
                    self.reminders.values(), key=lambda r: r.target_time
                ):
                    time_remaining = reminder.get_time_remaining()
                    target_time = reminder.get_target_time_str()

                    results.append(
                        Result(
                            title=f"#{reminder.id}: {reminder.message}",
                            subtitle=f"In {time_remaining} (at {target_time})",
                            icon_markup=icons.timer_on,
                            action=lambda rid=reminder.id: self._cancel_reminder(rid),
                            relevance=1.0,
                            plugin_name=self.display_name,
                            data={"type": "active_reminder", "id": reminder.id},
                        )
                    )

            return results

        # Handle cancel command
        if query.lower().startswith("cancel") or query.lower().startswith("stop"):
            parts = query.split()
            if len(parts) == 1:
                # Cancel all reminders
                count = self._cancel_reminder()
                results.append(
                    Result(
                        title=f"Cancelled {count} Reminders",
                        subtitle="All active reminders have been cancelled",
                        icon_markup=icons.timer_off,
                        action=lambda: None,
                        relevance=1.0,
                        plugin_name=self.display_name,
                        data={"type": "cancel_all"},
                    )
                )
            else:
                # Try to cancel specific reminder by ID
                try:
                    reminder_id = int(parts[1])
                    count = self._cancel_reminder(reminder_id)
                    if count > 0:
                        results.append(
                            Result(
                                title=f"Cancelled Reminder #{reminder_id}",
                                subtitle="Reminder has been cancelled",
                                icon_markup=icons.timer_off,
                                action=lambda: None,
                                relevance=1.0,
                                plugin_name=self.display_name,
                                data={"type": "cancel_specific"},
                            )
                        )
                    else:
                        results.append(
                            Result(
                                title="Reminder Not Found",
                                subtitle=f"No reminder with ID #{reminder_id}",
                                icon_markup=icons.alert,
                                action=lambda: None,
                                relevance=0.5,
                                plugin_name=self.display_name,
                                data={"type": "error"},
                            )
                        )
                except ValueError:
                    results.append(
                        Result(
                            title="Invalid Reminder ID",
                            subtitle="Please provide a valid reminder ID number",
                            icon_markup=icons.alert,
                            action=lambda: None,
                            relevance=0.5,
                            plugin_name=self.display_name,
                            data={"type": "error"},
                        )
                    )

            return results

        # Handle setting new reminders
        parts = query.split(None, 1)
        if len(parts) >= 1:
            time_str = parts[0]
            message = parts[1] if len(parts) > 1 else "Reminder"

            # Try to parse the time (but don't create the reminder yet!)
            target_time = self._parse_time_input(time_str)
            if target_time:
                # Calculate delay and check if it's valid
                delay = (target_time - datetime.now()).total_seconds()
                if delay > 0:
                    # Show what would happen, but don't create the reminder yet
                    time_remaining = self._format_time_remaining(delay)
                    target_time_str = target_time.strftime("%H:%M")

                    results.append(
                        Result(
                            title=f"Set Reminder: {message}",
                            subtitle=f"Will remind in {time_remaining} (at {
                                target_time_str
                            })",
                            icon_markup=icons.timer_on,
                            action=lambda ts=time_str, msg=message: self._create_and_confirm_reminder(
                                ts, msg
                            ),
                            relevance=1.0,
                            plugin_name=self.display_name,
                            data={
                                "type": "preview",
                                "time_str": time_str,
                                "message": message,
                            },
                        )
                    )
                else:
                    results.append(
                        Result(
                            title="Time is in the Past",
                            subtitle="Please specify a future time",
                            icon_markup=icons.alert,
                            action=lambda: None,
                            relevance=0.5,
                            plugin_name=self.display_name,
                            data={"type": "error"},
                        )
                    )
            else:
                # Invalid time format
                results.append(
                    Result(
                        title="Invalid Time Format",
                        subtitle="Use formats like: 5m, 30s, 2h, 14:30, or '5 minutes'",
                        icon_markup=icons.alert,
                        action=lambda: None,
                        relevance=0.5,
                        plugin_name=self.display_name,
                        data={"type": "error"},
                    )
                )

        return results
