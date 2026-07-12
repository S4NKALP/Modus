from typing import cast

from fabric.notifications import Notification, Notifications
from fabric.utils import (
    GdkPixbuf,
    GLib,
    Gtk,
    idle_add,
    invoke_repeater,
    os,
    re,
    remove_handler,
)
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.flowbox import FlowBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.overlay import Overlay
from fabric.widgets.revealer import Revealer
from fabric.widgets.wayland import WaylandWindow as Window

from services.config_watcher import (
    get_all_config,
    get_config_value,
    has_config_changed,
    on_config_change,
)
from utils.animatedscrollable import AnimatedScrollable
from utils.clippingbox import ClippingBox
from utils.corners import expanded_corner
from utils.functions import add_style_class_lazy, get_children_height_limit

DEFAULT_ICONS_THEME = Gtk.IconTheme.get_default()


def parse_timeout_to_ms(timeout: str | int) -> int:
    if isinstance(timeout, int):
        return timeout

    if isinstance(timeout, str):
        timeout_str = timeout.strip().lower()
        # Match patterns like "5s", "1m", "1h", "30s", etc.
        match = re.match(r"^(\d+(?:\.\d+)?)([hms]?)$", timeout_str)
        if match:
            value = float(match.group(1))
            unit = match.group(2) or "s"
            # Convert to milliseconds
            multipliers = {"h": 3600 * 1000, "m": 60 * 1000, "s": 1000, "": 1000}
            return int(value * multipliers.get(unit, 1000))

    raise ValueError(
        f"Invalid timeout format: {timeout}. Expected integer (ms) or string like '5s', '1m', '1h'"
    )


class LimitBox(Box):
    """A hack for replicating CSS's `max-*` properties"""

    def __init__(self, max_width: int, max_height: int, **kwargs):
        super().__init__(**kwargs)
        self.max_width: int = max_width
        self.max_height: int = max_height

    def do_size_allocate(self, allocation):
        if self.max_width >= 0:
            allocation.width = min(self.max_width, allocation.width)
        if self.max_height >= 0:
            allocation.height = min(self.max_height, allocation.height)
        return Box.do_size_allocate(self, allocation)


class NotificationItem(Box):
    def __init__(
        self,
        notification: Notification,
        image_size: int,
        timeout: int,
        width: int,
        buttons_per_row: int,
        **kwargs,
    ):
        super().__init__(
            name="notification",
            spacing=8,
            orientation="v",
            size=(width, -1),
            **kwargs,
        )

        self.notification = notification
        self._image_size = image_size
        self._timeout = timeout
        self._width = width
        self._buttons_per_row = buttons_per_row
        self._timeout_source_id: int | None = None

        body_container = Box(spacing=4, orientation="h")

        if image_pixbuf := self._load_notification_image():
            body_container.add(
                ClippingBox(
                    children=(
                        Image(
                            pixbuf=image_pixbuf,
                            v_align="fill",
                            h_align="fill",
                            v_expand=True,
                            h_expand=True,
                        )
                    ),
                    v_align="start",
                    h_align="start",
                    v_expand=False,
                    h_expand=False,
                    size=(self._image_size, self._image_size),
                    style=f"border-radius: {self._image_size // 2}px;",
                )
            )

        body_container.add(
            Box(
                spacing=4,
                orientation="v",
                children=[
                    # a box for holding both the "summary" label and the "close" button
                    Box(
                        orientation="h",
                        children=[
                            Overlay(
                                child=Label(
                                    label=self.notification.summary,
                                    style_classes="summary",
                                    ellipsization="middle",
                                )
                                .build()
                                .set_xalign(0.0)
                                .unwrap(),
                                # notification's source icon
                                overlays=[
                                    Image(
                                        # render app's icon if found
                                        pixbuf=icn.load_icon()
                                        if (
                                            icn := DEFAULT_ICONS_THEME.lookup_icon(
                                                self.notification.app_icon
                                                or self.notification.app_name,
                                                12,
                                                Gtk.IconLookupFlags.FORCE_SIZE,
                                            )
                                        )
                                        is not None
                                        else None,
                                        v_align="start",
                                        h_align="start",
                                    )
                                ],
                            ),
                        ],
                        h_expand=True,
                        v_expand=True,
                        v_align="start",
                    )
                    # add the "close" button
                    .build(
                        lambda box, _: box.pack_end(
                            Button(
                                image=Image(
                                    icon_name="close-symbolic",
                                    icon_size=18,
                                ),
                                v_align="center",
                                h_align="end",
                                on_clicked=lambda *_: self.notification.close(),
                                on_state_flags_changed=lambda btn, *_: (
                                    btn.set_cursor("pointer")
                                    if btn.get_state_flags() & 2 and btn.get_realized()
                                    else btn.set_cursor("default")
                                    if btn.get_realized()
                                    else None,
                                ),
                            ),
                            False,
                            False,
                            0,
                        )
                    ),
                    Label(
                        label=self.notification.body,
                        style_classes="body",
                        line_wrap="word-char",
                        v_align="start",
                        h_align="start",
                    )
                    .build()
                    .set_xalign(0.0)
                    .unwrap(),
                ],
                h_expand=True,
                v_expand=True,
            )
        )

        self.add(body_container)

        if actions := self.notification.actions:
            self.add(
                FlowBox(
                    spacing=4,
                    row_spacing=4,
                    column_spacing=4,
                    orientation="h",
                    v_expand=True,
                    h_expand=True,
                    children=[
                        Button(
                            h_expand=True,
                            v_expand=True,
                            label=action.label,
                            on_clicked=lambda *_, action=action: action.invoke(),
                            on_state_flags_changed=lambda btn, *_: (
                                btn.set_cursor("pointer")
                                if btn.get_state_flags() & 2 and btn.get_realized()
                                else btn.set_cursor("default")
                                if btn.get_realized()
                                else None,
                            ),
                        )
                        for action in actions
                    ],
                )
                .build()
                .set_max_children_per_line(min(len(actions), self._buttons_per_row))
                .unwrap()
            )

        # automatically close the notification after the timeout period
        self._start_timeout()

        add_style_class_lazy(self, "shine")

    def _start_timeout(self):
        if self._timeout_source_id is not None:
            remove_handler(self._timeout_source_id)
            self._timeout_source_id = None

        self._timeout_source_id = invoke_repeater(
            self._timeout,
            self.notification.close,
            "expired",
            initial_call=False,
        )

    def update_timeout(self, new_timeout: int):
        if self._timeout != new_timeout:
            self._timeout = new_timeout
            self._start_timeout()

    def _load_notification_image(self) -> GdkPixbuf.Pixbuf | None:
        if image_pixbuf := self.notification.image_pixbuf:
            return self._scale_pixbuf(image_pixbuf)

        if image_file := self._get_image_file_path():
            return self._load_image_from_file(image_file)

        return None

    def _get_image_file_path(self) -> str | None:
        try:
            if image_file := self.notification.get_image_file():
                return image_file
        except (AttributeError, TypeError):
            pass

        try:
            if image_file := getattr(self.notification, "image_file", None):
                return image_file
        except (AttributeError, TypeError):
            pass

        if image_file := self._get_hint_string("image-path"):
            return image_file

        try:
            app_icon = getattr(self.notification, "app_icon", None)
            if app_icon and os.path.exists(app_icon):
                return app_icon
        except (AttributeError, TypeError):
            pass

        return None

    def _get_hint_string(self, hint_name: str) -> str | None:
        try:
            hint_entry = self.notification.do_get_hint_entry(hint_name)
            if not hint_entry:
                return None

            if hasattr(hint_entry, "get_variant"):
                variant = hint_entry.get_variant()
                if variant and variant.is_of_type(GLib.VariantType.new("s")):
                    return variant.get_string()[0]

            if hasattr(hint_entry, "get_string"):
                return hint_entry.get_string()
        except (AttributeError, TypeError, Exception):
            pass
        return None

    def _load_image_from_file(self, image_file: str) -> GdkPixbuf.Pixbuf | None:
        if not (image_path := self._normalize_image_path(image_file)):
            return None

        paths_to_try = [image_path] + (
            [os.path.abspath(image_path)] if not os.path.isabs(image_path) else []
        )

        for path in paths_to_try:
            if not os.path.exists(path):
                continue
            try:
                return GdkPixbuf.Pixbuf.new_from_file_at_size(
                    path, self._image_size, self._image_size
                )
            except (GLib.GError, Exception):
                continue
        return None

    def _normalize_image_path(self, image_file: str) -> str | None:
        if not image_file:
            return None

        image_file = image_file[7:] if image_file.startswith("file://") else image_file
        return os.path.expanduser(image_file)

    def _scale_pixbuf(self, pixbuf: GdkPixbuf.Pixbuf) -> GdkPixbuf.Pixbuf:
        """Scale pixbuf to notification image size if needed"""
        if (
            pixbuf.get_width() == self._image_size
            and pixbuf.get_height() == self._image_size
        ):
            return pixbuf

        return pixbuf.scale_simple(
            self._image_size, self._image_size, GdkPixbuf.InterpType.BILINEAR
        )


# TODO: add the whole thing to a revealer that reveals to the left
class NotificationsView(Box):
    def __init__(self, **kwargs):
        super().__init__(orientation="v", visible=False, **kwargs)

        self._notification_items: list[NotificationItem] = []

        self._load_config()
        on_config_change(self._on_config_change)

        self.viewport = Box(spacing=4, orientation="v")

        self.scrolled_window = AnimatedScrollable(
            min_content_size=(420, 1),
            max_content_size=(420, 480),
            h_scrollbar_policy="never",
            v_scrollbar_policy="never",
            child=self.viewport,
            h_expand=True,
            v_expand=True,
        )

        self.overall_container = Box(
            name="notifications",
            orientation="v",
            children=ClippingBox(
                style_classes="notifications-clip", children=self.scrolled_window
            ),
            h_expand=True,
            v_expand=True,
        )

        self.notifications = Notifications(
            on_notification_added=lambda _, notification_id: (
                notification := cast(
                    Notification, self.notifications.notifications.get(notification_id)
                ),
                self._enabled
                and (
                    notification_item := NotificationItem(
                        notification,
                        self._image_size,
                        self._timeout,
                        self._width,
                        self._buttons_per_row,
                    ),
                    self._notification_items.append(notification_item),
                    self.viewport.add(
                        item_rev := Revealer(
                            child=notification_item,
                            reveal_child=False,
                            transition_type="slide-down",
                            transition_duration=self._revealer_duration,
                        )
                    ),
                    self.viewport.reorder_child(item_rev, 0),
                    # ready to show
                    item_rev.reveal(),
                    notification.closed.connect(
                        lambda: (
                            self._notification_items.remove(notification_item)
                            if notification_item in self._notification_items
                            else None,
                            item_rev.connect(
                                "notify::child-revealed",
                                lambda: item_rev.destroy()
                                if not item_rev.fully_revealed
                                else None,
                            ),
                            idle_add(item_rev.unreveal),
                        )
                    ),
                )
                or None,
            ),
        )

        self.children = (
            Box(
                orientation="h",
                children=[
                    Box(
                        orientation="v",
                        spacing=self._corner_size,
                        children=[
                            LimitBox(
                                max_width=self._corner_size,
                                max_height=self._corner_size,
                                children=expanded_corner(orientation="top-right"),
                                v_expand=True,
                                size=(self._corner_size, -1),
                            ),
                            Box(
                                h_expand=True,
                                v_expand=True,
                            ),
                        ],
                        h_expand=True,
                        v_expand=True,
                    ),
                    self.overall_container,
                ],
            ),
            Box(
                children=expanded_corner(orientation="top-right"),
                size=self._corner_size,
                h_align="end",
                v_align="end",
            ),
        )

        self.viewport.connect("add", self.on_children_change)
        self.viewport.connect("remove", self.on_children_change)
        self.connect("notify::visible", self.on_visiblity_change)

    def on_children_change(self, *_):
        self.scrolled_window.animate_size(
            get_children_height_limit(
                self.viewport,
                4,
                lambda rev: (
                    cast(Revealer, rev).get_child().get_preferred_size().minimum_size  # type: ignore
                ),
            )
        )

        if not self._enabled:
            return self.hide()

        return self.hide() if not self.viewport.children else self.show()

    def on_visiblity_change(self, *_):
        self.viewport.remove_style_class("popped")

        if not self.get_visible():
            return

        return add_style_class_lazy(self.viewport, "popped")

    def _load_config(self):
        config = get_all_config()
        self._enabled = get_config_value(config, "notifications.enabled", True)
        timeout_value = get_config_value(config, "notifications.timeout", "10s")
        self._timeout = parse_timeout_to_ms(timeout_value)
        self._image_size = get_config_value(config, "notifications.image_size", 64)
        self._width = get_config_value(config, "notifications.width", 360)
        self._buttons_per_row = get_config_value(
            config, "notifications.buttons_per_row", 2
        )
        self._corner_size = get_config_value(config, "notifications.corner_size", 16)
        self._revealer_duration = get_config_value(
            config, "notifications.revealer_duration", 400
        )

    def _on_config_change(self, new_config, old_config):
        enabled_changed = has_config_changed(
            old_config, new_config, "notifications.enabled"
        )
        timeout_changed = has_config_changed(
            old_config, new_config, "notifications.timeout"
        )
        image_size_changed = has_config_changed(
            old_config, new_config, "notifications.image_size"
        )
        width_changed = has_config_changed(
            old_config, new_config, "notifications.width"
        )
        buttons_per_row_changed = has_config_changed(
            old_config, new_config, "notifications.buttons_per_row"
        )
        corner_size_changed = has_config_changed(
            old_config, new_config, "notifications.corner_size"
        )
        revealer_duration_changed = has_config_changed(
            old_config, new_config, "notifications.revealer_duration"
        )

        if (
            enabled_changed
            or timeout_changed
            or image_size_changed
            or width_changed
            or buttons_per_row_changed
            or corner_size_changed
            or revealer_duration_changed
        ):
            old_timeout = self._timeout
            old_enabled = self._enabled
            self._load_config()

            if enabled_changed and self._enabled != old_enabled:
                if not self._enabled:
                    for item in list(self._notification_items):
                        item.notification.close()

            if timeout_changed and self._timeout != old_timeout:
                for item in self._notification_items:
                    item.update_timeout(self._timeout)


class NotificationWindow(Window):
    def __init__(self, **kwargs):
        super().__init__(
            layer="top",
            anchor="top right",
            visible=False,
            all_visible=False,
        )

        self.build(
            lambda win, _: win.add(
                NotificationsView().build(
                    lambda notifs, _: notifs.bind("visible", "visible", win)
                )
            )
        )
