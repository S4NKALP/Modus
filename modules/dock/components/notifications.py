import json
import os
from datetime import datetime

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow
from gi.repository import Gdk, GLib, Gtk

import config.data as data
import utils.icons as icons
from modules.notification_popup import NotificationBox
from utils.custom_image import CustomImage
from utils.notification_utils import (
    CONFIG_FILE,
    PERSISTENT_DIR,
    PERSISTENT_HISTORY_FILE,
    cleanup_orphan_cached_images,
    compute_time_label,
    create_historical_notification_from_data,
    get_date_header,
    get_shared_notification_history,
    load_scaled_pixbuf,
    save_persistent_history,
    schedule_midnight_update,
)
from utils.wayland import WaylandWindow as Window


class NotificationIndicator(Button):
    def __init__(self, **kwargs):
        super().__init__(name="button-bar-notifications", **kwargs)

        self.notification_icon = Label(
            name="notification-icon", markup=icons.notifications
        )

        self.add(self.notification_icon)

        self.connect("clicked", self.on_clicked)

        self.set_tooltip_text("Notifications")

        self.popup_window = None

        self._connect_to_dnd_state()

    def on_clicked(self, _button):
        if self.popup_window and self.popup_window.get_visible():
            self.popup_window.set_visible(False)
        else:
            self.show_notifications_popup()

    def show_notifications_popup(self):
        if self.popup_window:
            self.popup_window.destroy()

        self.popup_window = NotificationHistoryWindow()
        self.popup_window.show_all()

    def _connect_to_dnd_state(self):
        try:
            self.notification_history = get_shared_notification_history()

            self.notification_history.connect(
                "dnd-state-changed", self._on_dnd_state_changed
            )

            self._update_icon_for_dnd_state(
                self.notification_history.do_not_disturb_enabled
            )
        except Exception as e:
            print(f"Could not connect to DND state: {e}")

    def _on_dnd_state_changed(self, notification_history, dnd_enabled):
        self._update_icon_for_dnd_state(dnd_enabled)

    def _update_icon_for_dnd_state(self, dnd_enabled):
        if dnd_enabled:
            self.notification_icon.set_markup(icons.notifications_off)
            self.set_tooltip_text("Do Not Disturb enabled")
        else:
            self.notification_icon.set_markup(icons.notifications)
            self.set_tooltip_text("Notifications")


class NotificationHistory(Box):
    def __init__(self, **kwargs):
        super().__init__(name="notification-history", orientation="v", **kwargs)

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
        self.scrolled_window_viewport_box = Box(
            orientation="v",
            children=[self.notifications_list, self.no_notifications_box],
        )
        self.scrolled_window.add_with_viewport(self.scrolled_window_viewport_box)
        self.persistent_notifications = []
        self.add(self.history_header)
        self.add(self.scrolled_window)
        self._load_persistent_history()
        cleanup_orphan_cached_images(self.persistent_notifications)
        self.schedule_midnight_update()

        self._connect_to_shared_history()

        self._load_and_sync_dnd_state()

        self.LIMITED_APPS_HISTORY = ["Spotify"]

    def _connect_to_shared_history(self):
        try:
            shared_history = get_shared_notification_history()
            shared_history.connect(
                "notification-added", self._on_shared_notification_added
            )
        except Exception as e:
            print(f"Could not connect to shared notification history: {e}")

    def _on_shared_notification_added(self, shared_history):
        GLib.idle_add(self._refresh_history)

    def _refresh_history(self):
        try:
            for child in self.notifications_list.get_children()[:]:
                self.notifications_list.remove(child)
                if hasattr(child, "destroy"):
                    child.destroy()

            self.containers.clear()

            if os.path.exists(PERSISTENT_HISTORY_FILE):
                with open(PERSISTENT_HISTORY_FILE, "r") as f:
                    self.persistent_notifications = json.load(f)

                for note in reversed(self.persistent_notifications[-50:]):
                    self._add_historical_notification(note)

            self.update_no_notifications_label_visibility()
        except Exception as e:
            print(f"Error refreshing notification history: {e}")

    def _load_and_sync_dnd_state(self):
        try:
            dnd_enabled = False
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r") as f:
                    config_data = json.load(f)
                    dnd_enabled = config_data.get("dnd_enabled", False)

            shared_history = get_shared_notification_history()
            shared_history.do_not_disturb_enabled = dnd_enabled

            self.header_switch.set_active(dnd_enabled)
            self.do_not_disturb_enabled = dnd_enabled

        except Exception as e:
            print(f"Could not sync DND state: {e}")

    def schedule_midnight_update(self):
        schedule_midnight_update(self.on_midnight)

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
            ],
        )

    def rebuild_with_separators(self):
        GLib.idle_add(self._do_rebuild_with_separators)

    def _do_rebuild_with_separators(self):
        children = list(self.notifications_list.get_children())
        for child in children:
            self.notifications_list.remove(child)

        current_date_header = None
        last_date_header = None
        for container in sorted(
            self.containers, key=lambda x: x.arrival_time, reverse=True
        ):
            arrival_time = container.arrival_time
            date_header = get_date_header(arrival_time)
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

        try:
            shared_history = get_shared_notification_history()
            shared_history.set_do_not_disturb_enabled(self.do_not_disturb_enabled)
        except Exception as e:
            print(f"Could not update shared DND state: {e}")

    def clear_history(self, *args):
        for child in self.notifications_list.get_children()[:]:
            container = child
            notif_box = (
                container.notification_box
                if hasattr(container, "notification_box")
                else None
            )
            if notif_box:
                notif_box.destroy(from_history_delete=True)
            self.notifications_list.remove(child)
            child.destroy()

        if os.path.exists(PERSISTENT_HISTORY_FILE):
            try:
                os.remove(PERSISTENT_HISTORY_FILE)

            except Exception as e:
                print(f"Error deleting persistent history file: {e}")

        self.persistent_notifications = []
        self.containers = []
        self.rebuild_with_separators()

    def _load_persistent_history(self):
        if not os.path.exists(PERSISTENT_DIR):
            os.makedirs(PERSISTENT_DIR, exist_ok=True)

        if os.path.exists(PERSISTENT_HISTORY_FILE):
            try:
                with open(PERSISTENT_HISTORY_FILE, "r") as f:
                    self.persistent_notifications = json.load(f)

                for note in reversed(self.persistent_notifications[-50:]):
                    self._add_historical_notification(note)

            except Exception as e:
                print(f"Error loading persistent history: {e}")
                self.persistent_notifications = []
        else:
            self.persistent_notifications = []

        GLib.idle_add(self.update_no_notifications_label_visibility)

    def _save_persistent_history(self):
        save_persistent_history(self.persistent_notifications)

    def update_no_notifications_label_visibility(self):
        has_notifications = bool(self.containers)
        self.no_notifications_box.set_visible(not has_notifications)
        self.notifications_list.set_visible(has_notifications)

    def _add_historical_notification(self, note):
        hist_notif = create_historical_notification_from_data(note)

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
                CustomImage(pixbuf=load_scaled_pixbuf(hist_box, 48, 48)),
                Box(v_expand=True),
            ],
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

        self.hist_notif_body_label = (
            Label(
                name="notification-body",
                markup=hist_notif.body,
                h_align="start",
                ellipsization="end",
                line_wrap="word-char",
            )
            if hist_notif.body
            else Box()
        )
        self.hist_notif_body_label.set_single_line_mode(
            True
        ) if hist_notif.body else None

        self.hist_notif_summary_box = Box(
            name="notification-summary-box",
            orientation="h",
            children=[
                self.hist_notif_summary_label,
                Box(
                    name="notif-sep",
                    h_expand=False,
                    v_expand=False,
                    h_align="center",
                    v_align="center",
                ),
                self.hist_notif_app_name_label,
                Box(
                    name="notif-sep",
                    h_expand=False,
                    v_expand=False,
                    h_align="center",
                    v_align="center",
                ),
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
            on_clicked=lambda *_: self.delete_historical_notification(
                hist_notif.id, container
            ),
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

        self._save_persistent_history()
        container.destroy()
        self.containers = [c for c in self.containers if c != container]
        self.rebuild_with_separators()


class NotificationHistoryWindow(Window):
    def __init__(self):
        self.notification_history = NotificationHistory()

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
            propagate_height=False,
        )

        main_box = Box(
            name="notifications-popup-main",
            orientation="v",
            spacing=8,
            h_expand=True,
            v_expand=True,
            children=[scrolled],
        )

        dock_position = data.DOCK_POSITION
        popup_anchor = self._get_popup_anchor(dock_position)

        margin = self._get_popup_margin(dock_position)

        super().__init__(
            anchor=popup_anchor,
            margin=margin,
            child=main_box,
            layer="top",
            exclusive=False,
            keyboard_mode="on-demand",
            visible=True,
            all_visible=True,
        )

        self.connect("button-press-event", self.on_button_press)
        self.connect("key-press-event", self.on_key_press)

        self.set_can_focus(True)
        self.grab_focus()

        self.set_tooltip_text(
            "Keyboard shortcuts:\n• Escape: Close popup\n• Ctrl+D: Toggle DND\n• Ctrl+A: Clear all notifications"
        )

    def _get_popup_anchor(self, dock_position):
        anchor_map = {
            "Top": "top",  # Dock at top -> popup at top right
            "Bottom": "bottom",  # Dock at bottom -> popup at bottom right
            "Left": "left",  # Dock at left -> popup at top left
            "Right": "right",  # Dock at right -> popup at top right
        }
        return anchor_map.get(dock_position, "bottom")

    def _get_popup_margin(self, dock_position):
        margin_map = {
            "Top": "60px 10px 10px 10px",
            "Bottom": "10px 10px 60px 10px",
            "Left": "10px 10px 10px 60px",
            "Right": "10px 60px 10px 10px",
        }
        return margin_map.get(dock_position, "10px 10px 10px 10px")

    def refresh_popup(self):
        pass

    def on_key_press(self, _widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.set_visible(False)
            return True

        elif event.state & Gdk.ModifierType.CONTROL_MASK and event.keyval == Gdk.KEY_d:
            current_dnd = self.notification_history.do_not_disturb_enabled
            self.notification_history.header_switch.set_active(not current_dnd)
            return True

        elif event.state & Gdk.ModifierType.CONTROL_MASK and event.keyval == Gdk.KEY_a:
            self.notification_history.clear_history()
            return True

        return False

    def on_button_press(self, _widget, _event):
        return False


class Notifications(Box):
    def __init__(self, **kwargs):
        super().__init__(
            orientation="h" if not data.VERTICAL else "v",
            spacing=4,
            children=[NotificationIndicator()],
            **kwargs,
        )
        self.show_all()
