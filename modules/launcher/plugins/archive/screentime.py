import json
import os
import subprocess
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path

from gi.repository import GLib, Gtk, Gdk
from fabric.utils.helpers import get_relative_path
import utils.icons as icons
from utils.icon_resolver import IconResolver
from modules.launcher.plugin_base import PluginBase
from modules.launcher.result import Result


class ScreenTimeBarWidget(Gtk.Box):
    """Custom widget to display screen time statistics like GNOME Digital Wellbeing."""

    def __init__(self, usage_data: Dict[str, float], total_time: float, weekly_data: Dict[str, float] = None):
        super().__init__(
            name="screentime-widget",
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12
        )

        # Compact size for summary view only
        self.set_size_request(540, 150)
        self.set_vexpand(False)
        self.set_hexpand(True)

        self.usage_data = usage_data
        self.total_time = total_time
        self.weekly_data = weekly_data or {}

        self.setup_ui()

    def setup_ui(self):
        """Setup the GNOME-style digital wellbeing UI."""
        # Main container with minimal padding for launcher
        main_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        main_container.set_margin_left(12)
        main_container.set_margin_right(12)
        main_container.set_margin_top(0)
        main_container.set_margin_bottom(0)

        # Header section with large time display
        self.create_header_section(main_container)

        # Summary cards section
        self.create_summary_cards(main_container)

        self.pack_start(main_container, True, True, 0)
        self.show_all()

    def create_header_section(self, container):
        """Create the main header with large time display."""
        header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        # Main title
        title_label = Gtk.Label()
        title_label.set_markup('<span size="medium" weight="bold">Digital Wellbeing</span>')
        title_label.set_halign(Gtk.Align.CENTER)
        title_label.get_style_context().add_class("screentime-title")

        # Large time display
        total_hours = int(self.total_time // 3600)
        total_minutes = int((self.total_time % 3600) // 60)

        time_display = Gtk.Label()
        if total_hours > 0:
            time_text = f"{total_hours}h {total_minutes}m"
        else:
            time_text = f"{total_minutes}m"

        time_display.set_markup(f'<span size="xx-large" weight="bold" color="#3584e4">{time_text}</span>')
        time_display.set_halign(Gtk.Align.CENTER)
        time_display.get_style_context().add_class("screentime-time-display")

        # Subtitle
        subtitle = Gtk.Label()
        subtitle.set_markup('<span color="#666666">Screen time today</span>')
        subtitle.set_halign(Gtk.Align.CENTER)

        header_box.pack_start(title_label, False, False, 0)
        header_box.pack_start(time_display, False, False, 0)
        header_box.pack_start(subtitle, False, False, 0)

        container.pack_start(header_box, False, False, 0)

    def create_summary_cards(self, container):
        """Create summary statistics cards."""
        if not self.usage_data:
            return

        cards_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        cards_box.set_homogeneous(True)

        # Most used app card
        most_used_app = max(self.usage_data.items(), key=lambda x: x[1])
        most_used_hours = int(most_used_app[1] // 3600)
        most_used_minutes = int((most_used_app[1] % 3600) // 60)
        most_used_time = f"{most_used_hours}h {most_used_minutes}m" if most_used_hours > 0 else f"{most_used_minutes}m"

        most_used_card = self.create_info_card("Most Used", most_used_app[0], most_used_time)

        # App count card
        app_count = len([app for app, time in self.usage_data.items() if time >= 60])  # Apps with 1+ minute
        app_count_card = self.create_info_card("Apps Used", str(app_count), "applications")

        # Average session card (estimate)
        if app_count > 0:
            avg_session = self.total_time / app_count / 60  # minutes
            avg_text = f"{int(avg_session)}m"
        else:
            avg_text = "0m"
        avg_card = self.create_info_card("Avg Session", avg_text, "per app")

        cards_box.pack_start(most_used_card, True, True, 0)
        cards_box.pack_start(app_count_card, True, True, 0)
        cards_box.pack_start(avg_card, True, True, 0)

        container.pack_start(cards_box, False, False, 0)

    def create_info_card(self, title, value, subtitle):
        """Create an information card widget."""
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card.get_style_context().add_class("screentime-card")
        card.set_margin_left(8)
        card.set_margin_right(8)
        card.set_margin_top(8)
        card.set_margin_bottom(8)

        title_label = Gtk.Label()
        title_label.set_markup(f'<span size="small" color="#666666">{title}</span>')
        title_label.set_halign(Gtk.Align.CENTER)

        value_label = Gtk.Label()
        value_label.set_markup(f'<span size="large" weight="bold">{value}</span>')
        value_label.set_halign(Gtk.Align.CENTER)
        value_label.set_ellipsize(3)  # ELLIPSIZE_END
        value_label.set_max_width_chars(12)

        subtitle_label = Gtk.Label()
        subtitle_label.set_markup(f'<span size="x-small" color="#888888">{subtitle}</span>')
        subtitle_label.set_halign(Gtk.Align.CENTER)

        card.pack_start(title_label, False, False, 0)
        card.pack_start(value_label, False, False, 0)
        card.pack_start(subtitle_label, False, False, 0)

        return card

    def create_app_usage_section(self, container):
        """Create the application usage section with grid layout."""
        if not self.usage_data:
            no_data_label = Gtk.Label()
            no_data_label.set_markup('<span color="#666666">No usage data available</span>')
            no_data_label.set_halign(Gtk.Align.CENTER)
            no_data_label.set_margin_top(20)
            container.pack_start(no_data_label, True, True, 0)
            return

        # Section title
        section_title = Gtk.Label()
        section_title.set_markup('<span weight="bold">App Usage</span>')
        section_title.set_halign(Gtk.Align.START)
        section_title.set_margin_top(8)

        # Scrollable area for app grid
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        scrolled.set_min_content_height(120)

        # Container for app grid
        self.grid_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        scrolled.add(self.grid_box)

        container.pack_start(section_title, False, False, 0)
        container.pack_start(scrolled, True, True, 0)

        self.create_app_grid()

    def create_app_grid(self):
        """Create grid layout for app usage display."""
        if not self.usage_data:
            return

        # Sort apps by usage time (descending)
        sorted_apps = sorted(
            self.usage_data.items(),
            key=lambda x: x[1],
            reverse=True
        )

        # Show top 12 apps in grid format
        max_apps = 12
        apps_to_show = [app for app in sorted_apps[:max_apps] if app[1] >= 60]  # 1+ minute

        if not apps_to_show:
            return

        # Create grid with 3 columns
        cols = 3
        rows = (len(apps_to_show) + cols - 1) // cols  # Ceiling division

        for row in range(rows):
            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            row_box.set_homogeneous(True)

            for col in range(cols):
                app_index = row * cols + col
                if app_index < len(apps_to_show):
                    app_name, usage_time = apps_to_show[app_index]
                    app_card = self.create_app_grid_card(app_name, usage_time)
                    row_box.pack_start(app_card, True, True, 0)
                else:
                    # Empty placeholder to maintain grid alignment
                    placeholder = Gtk.Box()
                    row_box.pack_start(placeholder, True, True, 0)

            self.grid_box.pack_start(row_box, False, False, 0)

    def create_app_grid_card(self, app_name: str, usage_time: float) -> Gtk.Box:
        """Create a grid card for application usage display."""
        # Main card container
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        card.get_style_context().add_class("screentime-grid-card")
        card.set_margin_left(1)
        card.set_margin_right(1)
        card.set_margin_top(1)
        card.set_margin_bottom(1)

        # Icon container
        icon_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        icon_container.set_halign(Gtk.Align.CENTER)

        # Get real application icon (compact size for launcher)
        icon_pixbuf = self.icon_resolver.get_icon_pixbuf(app_name.lower(), 32)
        if not icon_pixbuf:
            # Fallback to default application icon
            icon_pixbuf = self.icon_resolver.get_icon_pixbuf("application-x-executable", 32)

        if icon_pixbuf:
            icon_image = Gtk.Image()
            icon_image.set_from_pixbuf(icon_pixbuf)
            icon_image.set_size_request(32, 32)
        else:
            # Final fallback to colored box
            icon_image = Gtk.Box()
            icon_image.set_size_request(32, 32)
            icon_image.get_style_context().add_class("screentime-grid-icon")

        icon_container.pack_start(icon_image, False, False, 0)

        # App name
        display_name = app_name if len(app_name) <= 10 else app_name[:7] + "..."
        name_label = Gtk.Label()
        name_label.set_markup(f'<span weight="500" size="x-small">{display_name}</span>')
        name_label.set_halign(Gtk.Align.CENTER)
        name_label.set_ellipsize(3)  # ELLIPSIZE_END
        name_label.set_max_width_chars(10)

        # Usage time
        hours = int(usage_time // 3600)
        minutes = int((usage_time % 3600) // 60)
        time_text = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"

        time_label = Gtk.Label()
        time_label.set_markup(f'<span size="x-small" weight="500" color="#3584e4">{time_text}</span>')
        time_label.set_halign(Gtk.Align.CENTER)

        # Pack elements
        card.pack_start(icon_container, False, False, 0)
        card.pack_start(name_label, False, False, 0)
        card.pack_start(time_label, False, False, 0)

        return card

    def create_modern_app_bar(self, app_name: str, usage_time: float, max_time: float) -> Gtk.Box:
        """Create a modern GNOME-style application usage bar."""
        # Main container with rounded corners styling
        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        container.get_style_context().add_class("screentime-app-item")
        container.set_margin_left(4)
        container.set_margin_right(4)
        container.set_margin_top(4)
        container.set_margin_bottom(4)

        # Top row with app name and time
        top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)

        # App icon and name
        app_info_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        # Get real application icon
        icon_pixbuf = self.icon_resolver.get_icon_pixbuf(app_name.lower(), 32)
        if not icon_pixbuf:
            # Fallback to default application icon
            icon_pixbuf = self.icon_resolver.get_icon_pixbuf("application-x-executable", 32)

        if icon_pixbuf:
            icon_image = Gtk.Image()
            icon_image.set_from_pixbuf(icon_pixbuf)
            icon_image.set_size_request(32, 32)
        else:
            # Final fallback to colored box if no icon found
            icon_image = Gtk.Box()
            icon_image.set_size_request(32, 32)
            icon_image.get_style_context().add_class("screentime-app-icon")

        # App name with better typography
        display_name = app_name if len(app_name) <= 20 else app_name[:17] + "..."
        name_label = Gtk.Label()
        name_label.set_markup(f'<span weight="500">{display_name}</span>')
        name_label.set_halign(Gtk.Align.START)
        name_label.set_ellipsize(3)  # ELLIPSIZE_END

        app_info_box.pack_start(icon_image, False, False, 0)
        app_info_box.pack_start(name_label, False, False, 0)

        # Time and percentage info
        time_info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        time_info_box.set_halign(Gtk.Align.END)

        # Usage time
        hours = int(usage_time // 3600)
        minutes = int((usage_time % 3600) // 60)
        time_text = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"

        time_label = Gtk.Label()
        time_label.set_markup(f'<span weight="500">{time_text}</span>')
        time_label.set_halign(Gtk.Align.END)

        # Percentage of total time
        percentage = (usage_time / self.total_time * 100) if self.total_time > 0 else 0
        percentage_label = Gtk.Label()
        percentage_label.set_markup(f'<span size="small" color="#666666">{percentage:.0f}%</span>')
        percentage_label.set_halign(Gtk.Align.END)

        time_info_box.pack_start(time_label, False, False, 0)
        time_info_box.pack_start(percentage_label, False, False, 0)

        top_row.pack_start(app_info_box, False, False, 0)
        top_row.pack_start(time_info_box, True, True, 0)

        # Modern progress bar with rounded corners
        progress_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        progress_container.get_style_context().add_class("screentime-progress-container")

        progress_bar = Gtk.ProgressBar()
        progress_bar.set_fraction(usage_time / max_time if max_time > 0 else 0)
        progress_bar.set_show_text(False)
        progress_bar.set_size_request(-1, 6)
        progress_bar.get_style_context().add_class("screentime-progress")

        # Color based on usage intensity with modern colors
        if percentage > 25:
            progress_bar.get_style_context().add_class("high-usage")
        elif percentage > 10:
            progress_bar.get_style_context().add_class("medium-usage")
        else:
            progress_bar.get_style_context().add_class("low-usage")

        progress_container.pack_start(progress_bar, True, True, 0)

        container.pack_start(top_row, False, False, 0)
        container.pack_start(progress_container, False, False, 0)

        return container


class ScreenTimePlugin(PluginBase):
    """
    Screen time tracking plugin that monitors application usage.
    """

    def __init__(self):
        super().__init__()
        self.display_name = "Screen Time"
        self.description = "Track application usage and screen time"

        # Data storage - single JSON file
        self.data_file = get_relative_path("../../../config/json/screentime.json")

        # Icon resolver for application icons
        self.icon_resolver = IconResolver()

        # Current tracking state
        self.current_app = None
        self.current_start_time = None
        self.screentime_data = {"sessions": []}  # Main data structure

        # Threading for monitoring
        self.monitor_thread = None
        self.stop_monitoring = threading.Event()

        # Last activity time for session tracking
        self.last_activity_time = None

    def initialize(self):
        """Initialize the screen time plugin."""
        self.set_triggers(["screentime", "st"])
        self.load_data()
        self.start_monitoring()

    def cleanup(self):
        """Cleanup the screen time plugin."""
        self.stop_monitoring.set()
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        self.save_data()

    def load_data(self):
        """Load screentime data from the JSON file."""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r') as f:
                    self.screentime_data = json.load(f)
                    if "sessions" not in self.screentime_data:
                        self.screentime_data["sessions"] = []
            else:
                self.screentime_data = {"sessions": []}

            # Initialize today's session if it doesn't exist
            today = datetime.now().strftime("%Y-%m-%d")
            today_session = self.get_session_for_date(today)
            if not today_session:
                self.screentime_data["sessions"].append({
                    "date": today,
                    "active_time": 0,
                    "apps": {}
                })

        except Exception as e:
            print(f"ScreenTimePlugin: Error loading data: {e}")
            self.screentime_data = {"sessions": []}

    def save_data(self):
        """Save screentime data to the JSON file."""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.data_file), exist_ok=True)

            with open(self.data_file, 'w') as f:
                json.dump(self.screentime_data, f, indent=2)
        except Exception as e:
            print(f"ScreenTimePlugin: Error saving data: {e}")

    def get_session_for_date(self, date_str: str) -> Optional[Dict]:
        """Get session data for a specific date."""
        for session in self.screentime_data["sessions"]:
            if session["date"] == date_str:
                return session
        return None

    def get_today_active_time(self) -> float:
        """Get today's total active time in seconds."""
        today = datetime.now().strftime("%Y-%m-%d")
        session = self.get_session_for_date(today)
        return session["active_time"] if session else 0

    def update_today_active_time(self, additional_seconds: float):
        """Add time to today's active time."""
        today = datetime.now().strftime("%Y-%m-%d")
        session = self.get_session_for_date(today)

        if session:
            session["active_time"] += additional_seconds
        else:
            # Create new session for today
            self.screentime_data["sessions"].append({
                "date": today,
                "active_time": additional_seconds,
                "apps": {}
            })

    def update_app_usage(self, app_name: str, additional_seconds: float):
        """Add time to today's app usage."""
        today = datetime.now().strftime("%Y-%m-%d")
        session = self.get_session_for_date(today)

        if session:
            if "apps" not in session:
                session["apps"] = {}
            if app_name not in session["apps"]:
                session["apps"][app_name] = 0
            session["apps"][app_name] += additional_seconds
        else:
            # Create new session for today
            self.screentime_data["sessions"].append({
                "date": today,
                "active_time": 0,
                "apps": {app_name: additional_seconds}
            })

    def get_today_apps(self) -> Dict[str, float]:
        """Get today's app usage data."""
        today = datetime.now().strftime("%Y-%m-%d")
        session = self.get_session_for_date(today)
        return session.get("apps", {}) if session else {}

    def get_weekly_total(self) -> float:
        """Get total active time for the last 7 days."""
        today = datetime.now()
        total_time = 0

        for i in range(7):
            date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            session = self.get_session_for_date(date)
            if session:
                total_time += session["active_time"]

        return total_time

    def _get_yesterday_total(self) -> float:
        """Get yesterday's total active time."""
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        session = self.get_session_for_date(yesterday)
        return session["active_time"] if session else 0

    def start_monitoring(self):
        """Start background monitoring of active windows."""
        if self.monitor_thread and self.monitor_thread.is_alive():
            return

        self.stop_monitoring.clear()
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()

    def _monitor_loop(self):
        """Main monitoring loop that tracks active time and app usage."""
        while not self.stop_monitoring.wait(2.0):  # Check every 2 seconds
            try:
                current_time = time.time()
                current_app = self._get_active_window_class()

                # If app changed, record time for previous app
                if self.current_app and self.current_app != current_app:
                    if self.current_start_time:
                        elapsed = current_time - self.current_start_time
                        # Only count if elapsed time is reasonable (not more than 5 seconds)
                        if elapsed <= 5.0:
                            self.update_today_active_time(elapsed)
                            self.update_app_usage(self.current_app, elapsed)

                # Update current app tracking
                if current_app:
                    self.current_app = current_app
                    self.current_start_time = current_time
                else:
                    # No active window, reset tracking
                    self.current_app = None
                    self.current_start_time = None

                # Save data periodically (every 30 seconds)
                if int(current_time) % 30 == 0:
                    self.save_data()

            except Exception as e:
                print(f"ScreenTimePlugin: Error in monitor loop: {e}")
                time.sleep(5)  # Wait longer on error

    def _get_active_window_class(self) -> Optional[str]:
        """Get the class name of the currently active window."""
        try:
            result = subprocess.run(
                ["hyprctl", "-j", "activewindow"],
                capture_output=True,
                text=True,
                timeout=2
            )

            if result.returncode == 0:
                window_data = json.loads(result.stdout)
                # Use class name, fallback to title if class is empty
                app_class = window_data.get("class", "").strip()
                if not app_class:
                    app_class = window_data.get("title", "Unknown").strip()

                # Filter out empty or system windows
                if app_class and app_class not in ["", "Unknown", "Desktop"]:
                    return app_class

        except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
            print(f"ScreenTimePlugin: Error getting active window: {e}")

        return None

    def query(self, query_string: str) -> List[Result]:
        """Process screen time queries with GNOME Digital Wellbeing style."""
        results = []
        query = query_string.strip().lower()

        # Get today's data
        today_time = self.get_today_active_time()
        today_apps = self.get_today_apps()
        weekly_time = self.get_weekly_total()

        # Main screen time display (compact view)
        if not query or query in ["today", "stats", "usage", "wellbeing"]:
            today_hours = int(today_time // 3600)
            today_minutes = int((today_time % 3600) // 60)

            # Enhanced subtitle with more context
            if today_time > 0:
                subtitle = f"Today: {today_hours}h {today_minutes}m"

                # Add comparison with yesterday if available
                yesterday_total = self._get_yesterday_total()
                if yesterday_total > 0:
                    if today_time > yesterday_total:
                        diff = today_time - yesterday_total
                        diff_minutes = int(diff // 60)
                        subtitle += f" (+{diff_minutes}m vs yesterday)"
                    elif today_time < yesterday_total:
                        diff = yesterday_total - today_time
                        diff_minutes = int(diff // 60)
                        subtitle += f" (-{diff_minutes}m vs yesterday)"

                # Add weekly average
                weekly_avg = weekly_time / 7 if weekly_time > 0 else 0
                if weekly_avg > 0:
                    avg_hours = int(weekly_avg // 3600)
                    avg_minutes = int((weekly_avg % 3600) // 60)
                    avg_text = f"{avg_hours}h {avg_minutes}m" if avg_hours > 0 else f"{avg_minutes}m"
                    subtitle += f" • Weekly avg: {avg_text}/day"
            else:
                subtitle = "No screen time recorded today"

            results.append(
                Result(
                    title="Digital Wellbeing",
                    subtitle=subtitle,
                    icon_markup=icons.screentime,
                    action=lambda: None,
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={"type": "screentime_display"}
                )
            )

        # App list view (individual result items)
        elif query in ["list", "apps", "applications"]:
            if today_apps:
                # Sort apps by usage time (descending)
                sorted_apps = sorted(
                    today_apps.items(),
                    key=lambda x: x[1],
                    reverse=True
                )

                # Show top 12 apps as individual results
                for i, (app_name, usage_time) in enumerate(sorted_apps[:12]):
                    if usage_time < 60:  # Skip apps with less than 1 minute
                        continue

                    hours = int(usage_time // 3600)
                    minutes = int((usage_time % 3600) // 60)
                    time_text = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"

                    # Calculate percentage of total time
                    percentage = (usage_time / today_time * 100) if today_time > 0 else 0

                    subtitle = f"Used for {time_text} today ({percentage:.0f}%)"

                    # Get application icon
                    app_icon_pixbuf = self.icon_resolver.get_icon_pixbuf(app_name.lower(), 48)

                    results.append(
                        Result(
                            title=app_name,
                            subtitle=subtitle,
                            icon=app_icon_pixbuf,
                            icon_markup=icons.screentime if not app_icon_pixbuf else None,
                            action=lambda: None,
                            relevance=1.0 - (i * 0.1),  # Decrease relevance for lower usage
                            plugin_name=self.display_name,
                            data={"type": "app_usage_item", "app": app_name}
                        )
                    )
            else:
                results.append(
                    Result(
                        title="No App Usage Data",
                        subtitle="Start using applications to see usage statistics",
                        icon_markup=icons.info,
                        action=lambda: None,
                        relevance=0.8,
                        plugin_name=self.display_name,
                        data={"type": "no_data"}
                    )
                )

        # Weekly summary option
        elif query in ["week", "weekly"]:
            weekly_hours = int(weekly_time // 3600)
            weekly_minutes = int((weekly_time % 3600) // 60)
            daily_avg = weekly_time / 7
            avg_hours = int(daily_avg // 3600)
            avg_minutes = int((daily_avg % 3600) // 60)

            results.append(
                Result(
                    title="Weekly Screen Time",
                    subtitle=f"Total: {weekly_hours}h {weekly_minutes}m • Daily avg: {avg_hours}h {avg_minutes}m",
                    icon_markup=icons.calendar,
                    action=lambda: None,
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={"type": "weekly_stats"}
                )
            )

        # Show help if no data
        if not today_apps and not query:
            results.append(
                Result(
                    title="Digital Wellbeing",
                    subtitle="Start using applications to see your screen time statistics",
                    icon_markup=icons.info,
                    action=lambda: None,
                    relevance=0.8,
                    plugin_name=self.display_name,
                    data={"type": "help"}
                )
            )

        # Quick stats for specific app queries
        if query and query not in ["today", "stats", "usage", "wellbeing", "week", "weekly"]:
            matching_apps = [
                (app, time_spent) for app, time_spent in today_apps.items()
                if query in app.lower()
            ]

            for app_name, time_spent in matching_apps[:3]:
                hours = int(time_spent // 3600)
                minutes = int((time_spent % 3600) // 60)
                percentage = (time_spent / today_time * 100) if today_time > 0 else 0
                time_text = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"

                subtitle = f"Today: {time_text} ({percentage:.0f}%)"

                # Get application icon pixbuf
                app_icon_pixbuf = self.icon_resolver.get_icon_pixbuf(app_name.lower(), 48)

                results.append(
                    Result(
                        title=f"{app_name}",
                        subtitle=subtitle,
                        icon=app_icon_pixbuf,
                        icon_markup=icons.screentime if not app_icon_pixbuf else None,
                        action=lambda: None,
                        relevance=0.9,
                        plugin_name=self.display_name,
                        data={"type": "app_stat", "app": app_name}
                    )
                )

        return results


