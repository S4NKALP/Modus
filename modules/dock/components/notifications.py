import json
import locale
import os
import uuid
from datetime import datetime, timedelta

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow
from gi.repository import GdkPixbuf, GLib, Gtk
from loguru import logger

import config.data as data
import utils.icons as icons
from modules.notification_popup import NotificationBox, cache_notification_pixbuf, load_scaled_pixbuf
from utils.custom_image import CustomImage
from utils.wayland import WaylandWindow as Window

PERSISTENT_DIR = f"/tmp/{data.APP_NAME}/notifications"
PERSISTENT_HISTORY_FILE = os.path.join(PERSISTENT_DIR, "notification_history.json")


class NotificationIndicator(Button):
    def __init__(self, **kwargs):
        super().__init__(name="button-bar-notifications", **kwargs)

        # Create the notification icon
        self.notification_icon = Label(
            name="notification-icon",
            markup=icons.notifications
        )

        # Add the icon directly
        self.add(self.notification_icon)

        # Connect click handler
        self.connect("clicked", self.on_clicked)

        # Set default tooltip
        self.set_tooltip_text("Notifications")

        # Popup window for showing notifications
        self.popup_window = None

    def on_clicked(self, _button):
        """Handle click to show/hide notification popup."""
        if self.popup_window and self.popup_window.get_visible():
            self.popup_window.set_visible(False)
        else:
            self.show_notifications_popup()

    def show_notifications_popup(self):
        """Show popup window with notification history."""
        if self.popup_window:
            self.popup_window.destroy()

        print(f"[NotificationIndicator] Opening notification history popup")

        # Create popup window using the notification history directly
        self.popup_window = NotificationHistoryWindow()
        self.popup_window.show_all()


class HistoricalNotification(object):
    def __init__(self, id, app_icon, summary, body, app_name, timestamp, cached_image_path=None):
        self.id = id
        self.app_icon = app_icon
        self.summary = summary
        self.body = body
        self.app_name = app_name
        self.timestamp = timestamp
        self.cached_image_path = cached_image_path
        self.image_pixbuf = None
        self.actions = []
        self.cached_scaled_pixbuf = None


class NotificationHistory(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="notification-history",
            orientation="v",
            **kwargs
        )

        self.containers = []
        self.header_label = Label(
            name="nhh",
            label="Notifications",
            h_align="start",
            h_expand=True,
        )
        self.header_switch = Gtk.Switch(name="dnd-switch")
        self.header_switch.set_vexpand(False)
        self.header_switch.set_valign(Gtk.Align.CENTER)
        self.header_switch.set_active(False)
        self.header_clean = Button(
            name="nhh-button",
            child=Label(name="nhh-button-label", markup=icons.trash),
            on_clicked=self.clear_history,
        )
        self.do_not_disturb_enabled = False
        self.header_switch.connect("notify::active", self.on_do_not_disturb_changed)
        self.dnd_label = Label(name="dnd-label", markup=icons.notifications_off)

        self.history_header = CenterBox(
            name="notification-history-header",
            spacing=8,
            start_children=[self.header_switch, self.dnd_label],
            center_children=[self.header_label],
            end_children=[self.header_clean],
        )
        self.notifications_list = Box(
            name="notifications-list",
            orientation="v",
            spacing=4,
            h_expand=True,
            v_expand=True,
            h_align="fill",
            v_align="fill",
        )
        self.no_notifications_label = Label(
            name="no-notif",
            markup=icons.notifications_clear,
            v_align="fill",
            h_align="fill",
            v_expand=True,
            h_expand=True,
            justification="center",
        )
        self.no_notifications_box = Box(
            name="no-notifications-box",
            v_align="fill",
            h_align="fill",
            v_expand=True,
            h_expand=True,
            children=[self.no_notifications_label],
        )
        self.scrolled_window = ScrolledWindow(
            name="notification-history-scrolled-window",
            orientation="v",
            h_expand=True,
            v_expand=True,
            h_align="fill",
            v_align="fill",
            propagate_width=False,
            propagate_height=False,
        )
        self.scrolled_window_viewport_box = Box(orientation="v", children=[self.notifications_list, self.no_notifications_box])
        self.scrolled_window.add_with_viewport(self.scrolled_window_viewport_box)
        self.persistent_notifications = []
        self.add(self.history_header)
        self.add(self.scrolled_window)
        self._load_persistent_history()
        self._cleanup_orphan_cached_images()
        self.schedule_midnight_update()

        self.LIMITED_APPS_HISTORY = ["Spotify"]

    def get_ordinal(self, n):
        if 11 <= (n % 100) <= 13:
            return 'th'
        else:
            return {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')

    def get_date_header(self, dt):
        now = datetime.now()
        today = now.date()
        date = dt.date()
        if date == today:
            return "Today"
        elif date == today - timedelta(days=1):
            return "Yesterday"
        else:
            original_locale = locale.getlocale(locale.LC_TIME)
            try:
                locale.setlocale(locale.LC_TIME, ('en_US', 'UTF-8'))
            except locale.Error:
                locale.setlocale(locale.LC_TIME, 'C')
            try:
                day = dt.day
                ordinal = self.get_ordinal(day)
                month = dt.strftime("%B")
                if dt.year == now.year:
                    result = f"{month} {day}{ordinal}"
                else:
                    result = f"{month} {day}{ordinal}, {dt.year}"
            finally:
                locale.setlocale(locale.LC_TIME, original_locale)
            return result

    def schedule_midnight_update(self):
        now = datetime.now()
        next_midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
        delta_seconds = (next_midnight - now).total_seconds()
        GLib.timeout_add_seconds(int(delta_seconds), self.on_midnight)

    def on_midnight(self):
        self.rebuild_with_separators()
        self.schedule_midnight_update()
        return GLib.SOURCE_REMOVE

    def create_date_separator(self, date_header):
        return Box(
            name="notif-date-sep",
            children=[
                Label(
                    name="notif-date-sep-label",
                    label=date_header,
                    h_align="center",
                    h_expand=True,
                )
            ]
        )

    def rebuild_with_separators(self):
        GLib.idle_add(self._do_rebuild_with_separators)

    def _do_rebuild_with_separators(self):
        children = list(self.notifications_list.get_children())
        for child in children:
            self.notifications_list.remove(child)

        current_date_header = None
        last_date_header = None
        for container in sorted(self.containers, key=lambda x: x.arrival_time, reverse=True):
            arrival_time = container.arrival_time
            date_header = self.get_date_header(arrival_time)
            if date_header != current_date_header:
                sep = self.create_date_separator(date_header)
                self.notifications_list.add(sep)
                current_date_header = date_header
                last_date_header = date_header
            self.notifications_list.add(container)

        if not self.containers and last_date_header:
            for child in list(self.notifications_list.get_children()):
                if child.get_name() == "notif-date-sep":
                    self.notifications_list.remove(child)

        self.notifications_list.show_all()
        self.update_no_notifications_label_visibility()

    def on_do_not_disturb_changed(self, switch, pspec):
        self.do_not_disturb_enabled = switch.get_active()
        logger.info(f"Do Not Disturb mode {'enabled' if self.do_not_disturb_enabled else 'disabled'}")

    def clear_history(self, *args):
        for child in self.notifications_list.get_children()[:]:
            container = child
            notif_box = container.notification_box if hasattr(container, "notification_box") else None
            if notif_box:
                notif_box.destroy(from_history_delete=True)
            self.notifications_list.remove(child)
            child.destroy()

        # Clear notifications from the fabric service
        try:
            # Clear all notifications from the fabric service
            # Note: fabric Notifications doesn't have clear_all_notifications method
            # so we just clear our local history
            logger.info("Notification history cleared.")
        except Exception as e:
            logger.error(f"Error clearing notification history: {e}")

        # Also clear persistent file if it exists
        if os.path.exists(PERSISTENT_HISTORY_FILE):
            try:
                os.remove(PERSISTENT_HISTORY_FILE)
                logger.info("Notification history cleared and persistent file deleted.")
            except Exception as e:
                logger.error(f"Error deleting persistent history file: {e}")

        self.persistent_notifications = []
        self.containers = []
        self.rebuild_with_separators()

    def _load_persistent_history(self):
        """Load notifications from persistent file."""
        if not os.path.exists(PERSISTENT_DIR):
            os.makedirs(PERSISTENT_DIR, exist_ok=True)

        # Load from persistent file
        if os.path.exists(PERSISTENT_HISTORY_FILE):
            try:
                with open(PERSISTENT_HISTORY_FILE, "r") as f:
                    self.persistent_notifications = json.load(f)
                logger.info(f"Loading {len(self.persistent_notifications)} notifications from persistent history")

                # Add notifications to display (in reverse order to show newest first)
                for note in reversed(self.persistent_notifications[-50:]):  # Last 50 notifications
                    self._add_historical_notification(note)

            except Exception as e:
                logger.error(f"Error loading persistent history: {e}")
                self.persistent_notifications = []
        else:
            self.persistent_notifications = []

        GLib.idle_add(self.update_no_notifications_label_visibility)

    def _save_persistent_history(self):
        try:
            with open(PERSISTENT_HISTORY_FILE, "w") as f:
                json.dump(self.persistent_notifications, f)
        except Exception as e:
            logger.error(f"Error saving persistent history: {e}")

    def update_no_notifications_label_visibility(self):
        has_notifications = bool(self.containers)
        self.no_notifications_box.set_visible(not has_notifications)
        self.notifications_list.set_visible(has_notifications)

    def _cleanup_orphan_cached_images(self):
        logger.debug("Starting orphan cached image cleanup.")
        if not os.path.exists(PERSISTENT_DIR):
            logger.debug("Cache directory does not exist, skipping cleanup.")
            return

        cached_files = [f for f in os.listdir(PERSISTENT_DIR) if f.startswith("notification_") and f.endswith(".png")]
        if not cached_files:
            logger.debug("No cached image files found, skipping cleanup.")
            return

        history_uuids = {note.get("id") for note in self.persistent_notifications if note.get("id")}
        deleted_count = 0
        for cached_file in cached_files:
            try:
                uuid_from_filename = cached_file[len("notification_"):-len(".png")]
                if uuid_from_filename not in history_uuids:
                    cache_file_path = os.path.join(PERSISTENT_DIR, cached_file)
                    os.remove(cache_file_path)
                    logger.info(f"Deleted orphan cached image: {cache_file_path}")
                    deleted_count += 1
                else:
                    logger.debug(f"Cached image {cached_file} found in history, keeping it.")
            except Exception as e:
                logger.error(f"Error processing cached file {cached_file} during cleanup: {e}")

        if deleted_count > 0:
            logger.info(f"Orphan cached image cleanup finished. Deleted {deleted_count} images.")
        else:
            logger.info("Orphan cached image cleanup finished. No orphan images found.")

    def _add_historical_notification(self, note):
        hist_notif = HistoricalNotification(
            id=note.get("id"),
            app_icon=note.get("app_icon"),
            summary=note.get("summary"),
            body=note.get("body"),
            app_name=note.get("app_name"),
            timestamp=note.get("timestamp"),
            cached_image_path=note.get("cached_image_path"),
        )

        hist_box = NotificationBox(hist_notif, timeout_ms=0)
        hist_box.uuid = hist_notif.id
        hist_box.cached_image_path = hist_notif.cached_image_path
        hist_box.set_is_history(True)
        for child in hist_box.get_children():
            if child.get_name() == "notification-action-buttons":
                hist_box.remove(child)
        container = Box(
            name="notification-container",
            orientation="v",
            h_align="fill",
            h_expand=True,
        )
        container.notification_box = hist_box
        try:
            arrival = datetime.fromisoformat(hist_notif.timestamp)
        except Exception:
            arrival = datetime.now()
        container.arrival_time = arrival

        def compute_time_label(arrival_time):
            return arrival_time.strftime("%H:%M")

        self.hist_time_label = Label(
            name="notification-timestamp",
            markup=compute_time_label(container.arrival_time),
            h_align="start",
            ellipsization="end",
        )
        self.hist_notif_image_box = Box(
            name="notification-image",
            orientation="v",
            children=[
                CustomImage(
                    pixbuf=load_scaled_pixbuf(hist_box, 48, 48)
                ),
                Box(v_expand=True),
            ]
        )
        self.hist_notif_summary_label = Label(
            name="notification-summary",
            markup=hist_notif.summary,
            h_align="start",
            ellipsization="end",
        )

        self.hist_notif_app_name_label = Label(
            name="notification-app-name",
            markup=f"{hist_notif.app_name}",
            h_align="start",
            ellipsization="end",
        )

        self.hist_notif_body_label = Label(
            name="notification-body",
            markup=hist_notif.body,
            h_align="start",
            ellipsization="end",
            line_wrap="word-char",
        ) if hist_notif.body else Box()
        self.hist_notif_body_label.set_single_line_mode(True) if hist_notif.body else None

        self.hist_notif_summary_box = Box(
            name="notification-summary-box",
            orientation="h",
            children=[
                self.hist_notif_summary_label,
                Box(name="notif-sep", h_expand=False, v_expand=False, h_align="center", v_align="center"),
                self.hist_notif_app_name_label,
                Box(name="notif-sep", h_expand=False, v_expand=False, h_align="center", v_align="center"),
                self.hist_time_label,
            ],
        )
        self.hist_notif_text_box = Box(
            name="notification-text",
            orientation="v",
            v_align="center",
            h_expand=True,
            children=[
                self.hist_notif_summary_box,
                self.hist_notif_body_label,
            ],
        )
        self.hist_notif_close_button = Button(
            name="notif-close-button",
            child=Label(name="notif-close-label", markup=icons.cancel),
            on_clicked=lambda *_: self.delete_historical_notification(hist_notif.id, container),
        )
        self.hist_notif_close_button_box = Box(
            orientation="v",
            children=[
                self.hist_notif_close_button,
                Box(v_expand=True),
            ],
        )
        content_box = Box(
            name="notification-box-hist",
            spacing=8,
            children=[
                self.hist_notif_image_box,
                self.hist_notif_text_box,
                self.hist_notif_close_button_box,
            ],
        )
        container.add(content_box)
        self.containers.insert(0, container)
        self.rebuild_with_separators()
        self.update_no_notifications_label_visibility()

    def delete_historical_notification(self, note_id, container):
        if hasattr(container, "notification_box"):
            notif_box = container.notification_box
            notif_box.destroy(from_history_delete=True)

        target_note_id_str = str(note_id)

        new_persistent_notifications = []
        removed_from_list = False
        for note_in_list in self.persistent_notifications:
            current_note_id_str = str(note_in_list.get("id"))
            if current_note_id_str == target_note_id_str:
                removed_from_list = True
                continue
            new_persistent_notifications.append(note_in_list)

        if removed_from_list:
            self.persistent_notifications = new_persistent_notifications
            logger.info(f"Notification with ID {target_note_id_str} was marked for removal from persistent_notifications list.")
        else:
            logger.warning(f"Notification with ID {target_note_id_str} was NOT found in persistent_notifications list. The list remains unchanged.")

        self._save_persistent_history()
        container.destroy()
        self.containers = [c for c in self.containers if c != container]
        self.rebuild_with_separators()


class NotificationHistoryWindow(Window):
    def __init__(self):
        # Create the notification history widget directly
        self.notification_history = NotificationHistory()

        # Create scrolled window with proper sizing
        scrolled = ScrolledWindow(
            name="notifications-scrolled",
            child=self.notification_history,
            h_scrollbar_policy="never",
            v_scrollbar_policy="automatic",
            min_content_size=(400, 450),
            max_content_size=(450, 500),
            h_expand=True,
            v_expand=True,
            propagate_width=False,
            propagate_height=False
        )

        main_box = Box(
            name="notifications-popup-main",
            orientation="v",
            spacing=8,
            h_expand=True,
            v_expand=True,
            children=[scrolled]
        )

        # Determine popup position based on dock position
        dock_position = data.DOCK_POSITION
        popup_anchor = self._get_popup_anchor(dock_position)

        print(f"[NotificationPopup] Dock position: {dock_position}, Popup anchor: {popup_anchor}")

        # Get margin based on dock position
        margin = self._get_popup_margin(dock_position)

        super().__init__(
            name="notifications-popup-window",
            anchor=popup_anchor,
            margin=margin,
            child=main_box,
            layer="top",
            exclusive=False,
            keyboard_mode="on-demand",
            visible=True,
            all_visible=True
        )

        # Auto-hide when clicking outside or pressing escape
        self.connect("button-press-event", self.on_button_press)
        self.connect("key-press-event", self.on_key_press)

        # Make sure the window can receive key events
        self.set_can_focus(True)
        self.grab_focus()

        # Set tooltip with keyboard shortcuts
        self.set_tooltip_text("Keyboard shortcuts:\n• Escape: Close popup\n• Ctrl+D: Toggle DND\n• Ctrl+A: Clear all notifications")

    def _get_popup_anchor(self, dock_position):
        """Determine popup anchor position based on dock position."""
        # Position popup on the opposite side of the dock for better UX
        anchor_map = {
            "Top": "top",      # Dock at top -> popup at top right
            "Bottom": "bottom", # Dock at bottom -> popup at bottom right
            "Left": "left",      # Dock at left -> popup at top left
            "Right": "right"     # Dock at right -> popup at top right
        }
        return anchor_map.get(dock_position, "bottom")  # Default fallback

    def _get_popup_margin(self, dock_position):
        """Get appropriate margin based on dock position."""
        # Add margin to avoid overlapping with dock
        margin_map = {
            "Top": "60px 10px 10px 10px",     # Top dock -> margin from top
            "Bottom": "10px 10px 60px 10px",  # Bottom dock -> margin from bottom
            "Left": "10px 10px 10px 60px",    # Left dock -> margin from left
            "Right": "10px 60px 10px 10px"    # Right dock -> margin from right
        }
        return margin_map.get(dock_position, "10px 10px 10px 10px")  # Default fallback

    def refresh_popup(self):
        """Refresh the popup content by updating the notification history."""
        # The notification history will automatically update itself
        # when notifications are added/removed from the service
        pass

    def on_key_press(self, _widget, event):
        """Handle key press events."""
        from gi.repository import Gdk

        # Check if Escape key was pressed
        if event.keyval == Gdk.KEY_Escape:
            print(f"[NotificationPopup] Escape key pressed, closing popup")
            self.set_visible(False)
            return True  # Event handled

        # Check for Ctrl+D to toggle DND
        elif event.state & Gdk.ModifierType.CONTROL_MASK and event.keyval == Gdk.KEY_d:
            print(f"[NotificationPopup] Ctrl+D pressed, toggling DND")
            # Toggle DND via the notification history
            current_dnd = self.notification_history.do_not_disturb_enabled
            self.notification_history.header_switch.set_active(not current_dnd)
            return True  # Event handled

        # Check for Ctrl+A to clear all notifications
        elif event.state & Gdk.ModifierType.CONTROL_MASK and event.keyval == Gdk.KEY_a:
            print(f"[NotificationPopup] Ctrl+A pressed, clearing all notifications")
            self.notification_history.clear_history()
            return True  # Event handled

        return False  # Let other handlers process the event

    def on_button_press(self, _widget, _event):
        """Hide popup when clicking outside."""
        # This is a simple implementation - in a real scenario you'd want
        # more sophisticated outside-click detection
        return False



class Notifications(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="notifications",
            orientation="h" if not data.VERTICAL else "v",
            spacing=4,
            children=[NotificationIndicator()],
            **kwargs
        )
        self.show_all()
