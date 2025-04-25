from fabric.notifications import Notification
from services import notification_service
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from fabric.widgets.image import Image
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.widgets.revealer import Revealer
from loguru import logger
import utils.icons as icons
from gi.repository import GdkPixbuf, GLib
from utils import CustomImage
import os
from gi.repository import Gtk
from fabric.widgets.centerbox import CenterBox


class NotificationCenter(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="notification-center",
            visible=False,
            all_visible=False,
            **kwargs,
        )

        self.launcher = kwargs["launcher"]
        self.notification_service = notification_service

        # Main container for notifications
        self.notifications = Box(
            v_expand=True,
            h_expand=True,
            orientation="v",
            spacing=8,
        )
        self.header_switch = Gtk.Switch(name="matugen-switcher")
        self.header_switch.set_vexpand(False)
        self.header_switch.set_valign(Gtk.Align.CENTER)
        self.header_switch.set_active(self.notification_service.dont_disturb)
        self.do_not_disturb_enabled = self.notification_service.dont_disturb
        self.header_switch.connect("notify::active", self.on_do_not_disturb_changed)
        self.dnd_label = Label(name="dnd-label", markup=icons.notifications_off)
        # Header with clear all button
        header = CenterBox(
            h_expand=True,
            start_children=[self.header_switch, self.dnd_label],
            center_children=[
                Label(
                    label="Notifications",
                    name="nhh",
                )
            ],
            end_children=[
                Button(
                    name="nhh-button",
                    child=Label(name="nhh-button-label", markup=icons.trash),
                    on_clicked=lambda *args: self.clear_all_notifications(),
                )
            ],
        )

        self.scrolledwindow = ScrolledWindow(
            name="scrolled-window",
            child=self.notifications,
            min_content_size=(400, 300),
            max_content_size=(400, 300),
            v_expand=True,
            h_expand=True,
        )

        # Main container
        main_container = Box(
            v_expand=True,
            h_expand=True,
            orientation="v",
            children=[header, self.scrolledwindow],
        )

        self.add(main_container)

        # Connect to notification service signals
        self.notification_service.connect(
            "notification-added", self.on_new_notification
        )
        self.notification_service.connect("clear_all", self.on_clear_all)

        # Load existing notifications
        self.load_notifications()

    def load_notifications(self):
        """Load existing notifications from the service."""
        notifications = self.notification_service.get_deserialized()
        if not notifications:
            # Create a container box to better center the message
            container = Box(
                name="no-notifications-container",
                orientation="v",
                h_align="center",
                v_align="center",
                h_expand=True,
                v_expand=True,
            )

            # Show a message if no notifications
            label = Label(
                name="no-notifications-label",
                markup=icons.notifications_clear,
                v_align="fill",
                h_align="fill",
                v_expand=True,
                h_expand=True,
                justification="center",
            )

            container.add(label)
            self.notifications.add(container)
            return

        for notification in notifications:
            self.add_notification(notification)

    def toggle_notification_body(self, revealer, chevron_label):
        """Toggle the visibility of notification body."""
        is_revealed = revealer.get_reveal_child()
        revealer.set_reveal_child(not is_revealed)
        # Update chevron icon
        chevron_label.set_markup(
            icons.chevron_up if not is_revealed else icons.chevron_down
        )

    def add_notification(self, notification: Notification):
        """Add a notification to the center."""
        # Remove empty state container if it exists
        for child in self.notifications.get_children():
            if child.get_name() == "no-notifications-container":
                self.notifications.remove(child)
                break

        # Get timestamp from notification object
        timestamp = getattr(notification, 'timestamp', GLib.get_real_time() / 1000000)
        time_str = GLib.DateTime.new_from_unix_local(timestamp).format("%I:%M %p")

        # Create the notification header (summary) box
        header_box = Box(
            name="notification-header",
            # h_expand=True,
            spacing=8,
            children=[
                Box(
                    orientation="h",
                    h_expand=True,
                    spacing=8,
                    style="min-width: 0;",
                    children=[
                        # Summary
                        Label(
                            name="notification-app-name",
                            markup=notification.app_name + " | ",
                            h_align="start",
                            ellipsization="end",
                        ),
                        Label(
                            markup=notification.summary.replace("\n", " "),
                            h_align="start",
                            ellipsization="end",
                        ),
                        Label(
                            name="notification-time",
                            markup=f" | {time_str}",
                            h_align="end",
                            style="color: var(--outline);",
                        ),
                    ],
                ),
                # Add chevron button if there's content to show
                *(
                    [
                        Button(
                            name="chevron-button",
                            child=Label(
                                name="chevron-label", markup=icons.chevron_down
                            ),
                        )
                    ]
                    if notification.body or notification.image_pixbuf
                    else []
                ),
                Button(
                    name="notif-close-button",
                    child=Label(name="notif-close-label", markup=icons.cancel),
                    on_clicked=lambda *args: self.remove_notification(notification),
                ),
            ],
        )

        # Create content box that will be revealed
        # Create content box in vertical layout for body + actions
        content_box = Box(
            name="notification-content",
            spacing=8,
            orientation="v", 
        )

        # Create horizontal box for image and body
        body_box = Box(
            name="notification-body-box",
            spacing=8,
            orientation="h",
        )

        # Add image if available
        if notification.image_pixbuf:
            image_box = Box(
                name="notification-image",
                children=[
                    CustomImage(
                        pixbuf=notification.image_pixbuf.scale_simple(
                            48, 48, GdkPixbuf.InterpType.BILINEAR
                        )
                        if notification.image_pixbuf
                        else self.get_pixbuf(notification.app_icon, 48, 48)
                    ),
                ],
            )
            body_box.add(image_box)

        # Add body text if available
        if notification.body:
            body_box.add(
                Label(
                    markup=notification.body.replace("\n", " "),
                    name="notification-body",
                    h_align="start",
                    ellipsization="end",
                )
            )

        # Add body box to content
        content_box.add(body_box)

        # Add action buttons if available
        if notification.actions:
            action_box = Box(
                name="notification-action-buttons",
                spacing=4,
                h_expand=True,
            )
            for i, action in enumerate(notification.actions):
                style_class = (
                    "start-action"
                    if i == 0
                    else "end-action"
                    if i == len(notification.actions) - 1
                    else "middle-action"
                )
                button = Button(
                    name="action-button",
                    h_expand=True,
                    child=Label(name="button-label", label=action.label),
                    on_clicked=lambda btn, act=action, notif=notification: [
                        act.invoke(),
                        self.notification_service.remove_notification(notif.id),
                        self.remove_notification(notif)
                    ],
                )
                button.add_style_class(style_class)
                action_box.add(button)
            content_box.add(action_box)

        # Create revealer for content
        body_revealer = None
        if notification.body or notification.image_pixbuf:
            body_revealer = Revealer(
                name="body-revealer",
                transition_type="slide-down",
                reveal_child=False,
                child=content_box,
            )

        # Create main notification box
        notification_box = Box(
            name="notification-box",
            orientation="v",
            h_expand=True,
            style="margin: 4px; padding: 16px; border-radius: 20px; background-color: var(--surface-container-low); min-width: 200px;",
            children=[header_box],
        )

        # Add body revealer if exists
        if body_revealer:
            notification_box.add(body_revealer)
            # Get the chevron button from header_box children
            chevron_button = [
                c for c in header_box.get_children() if c.get_name() == "chevron-button"
            ][0]
            chevron_label = chevron_button.get_child()
            chevron_button.connect(
                "clicked",
                lambda *args: self.toggle_notification_body(
                    body_revealer, chevron_label
                ),
            )

        self.notifications.add(notification_box)

    def on_do_not_disturb_changed(self, switch, pspec):
        """Handle Do Not Disturb toggle."""
        self.do_not_disturb_enabled = switch.get_active()
        self.notification_service.dont_disturb = self.do_not_disturb_enabled

    def on_new_notification(self, fabric_notif, id):
        """Handle new notification event."""
        notification = fabric_notif.get_notification_from_id(id)
        self.add_notification(notification)

    def remove_notification(self, notification: Notification):
        """Remove a notification from the center."""
        self.notification_service.remove_notification(notification.id)
        # Find and remove the notification box
        for child in self.notifications.get_children():
            if child.get_name() == "notification-box":
                # Get the header box
                header_box = child.get_children()[0]
                # Get the text container box
                text_box = header_box.get_children()[0]
                # Get the summary label (second child of text box)
                summary_label = text_box.get_children()[1]
                if summary_label.get_text() == notification.summary:
                    self.notifications.remove(child)
                    break

    def clear_all_notifications(self, *args):
        """Clear all notifications."""
        self.notification_service.clear_all_notifications()
        # Remove all child widgets
        for child in self.notifications.get_children():
            self.notifications.remove(child)

        # Add empty state
        container = Box(
            name="no-notifications-container",
            orientation="v",
            h_align="center",
            v_align="center",
            h_expand=True,
            v_expand=True,
        )

        label = Label(
            name="no-notifications-label",
            markup=icons.notifications_clear,
            v_align="fill",
            h_align="fill",
            v_expand=True,
            h_expand=True,
            justification="center",
        )

        container.add(label)
        self.notifications.add(container)

    def on_clear_all(self, *args):
        """Handle clear all event from service."""
        # Remove all child widgets
        for child in self.notifications.get_children():
            self.notifications.remove(child)

        # Add empty state
        container = Box(
            name="no-notifications-container",
            orientation="v",
            h_align="center",
            v_align="center",
            h_expand=True,
            v_expand=True,
        )

        label = Label(
            name="no-notifications-label",
            markup=icons.notifications_clear,
            v_align="fill",
            h_align="fill",
            v_expand=True,
            h_expand=True,
            justification="center",
        )

        container.add(label)
        self.notifications.add(container)

    def get_pixbuf(self, icon_path, width, height):
        if icon_path.startswith("file://"):
            icon_path = icon_path[7:]

        if not os.path.exists(icon_path):
            logger.warning(f"Icon path does not exist: {icon_path}")
            return None

        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file(icon_path)
            return pixbuf.scale_simple(width, height, GdkPixbuf.InterpType.BILINEAR)
        except Exception as e:
            logger.error(f"Failed to load or scale icon: {e}")
            return None

    def open_center(self):
        """Open the notification center."""
        self.show_all()
