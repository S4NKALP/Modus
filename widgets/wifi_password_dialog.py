import gi
from gi.repository import Gdk, GLib

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from widgets.wayland import WaylandWindow as Window

gi.require_version("Gtk", "3.0")


class WiFiPasswordDialog(Window):
    def __init__(
        self,
        ssid: str,
        on_connect_callback=None,
        on_cancel_callback=None,
        on_dialog_closed=None,
        **kwargs,
    ):
        super().__init__(
            title="modus",
            layer="overlay",
            anchor="center",
            keyboard_mode="on-demand",
            visible=False,
            name="wifi-password-dialog",
            **kwargs,
        )

        self.ssid = ssid
        self.on_connect_callback = on_connect_callback
        self.on_cancel_callback = on_cancel_callback
        self.on_dialog_closed = on_dialog_closed
        self.is_connecting = False
        self.connection_timeout_id = None

        self._create_dialog_content()
        self.connect("key-press-event", self._on_key_press)
        self.connect("notify::visible", self._on_visibility_changed)

    def _create_dialog_content(self):
        self.wifi_icon = Image(
            icon_name="network-wireless-symbolic", size=20, name="wifi-dialog-icon"
        )

        self.title_label = Label(
            label=f'The Wi-Fi network "{self.ssid}" requires a WPA2 password.',
            name="wifi-dialog-title",
            h_align="start",
            wrap=True,
            max_width_chars=40,
        )

        self.title_container = Box(
            orientation="h",
            spacing=8,
            children=[self.wifi_icon, self.title_label],
            name="wifi-dialog-title-container",
            h_align="center",
        )

        self.error_label = Label(
            label="Incorrect password. Please try again.",
            name="wifi-dialog-error",
            h_align="center",
            visible=False,
        )

        self.password_label = Label(
            label="Password:", name="wifi-dialog-password-label", h_align="start"
        )

        self.password_entry = Entry(
            placeholder_text="Enter password",
            name="wifi-dialog-password-entry",
            visibility=False,
            h_expand=True,
        )

        self.password_entry.connect("activate", lambda *_: self._on_join_clicked())
        self.password_entry.connect("changed", self._on_password_changed)

        self.password_visible = False
        self.show_password_button = Button(
            image=Image(icon_name="view-conceal-symbolic", size=16),
            name="wifi-dialog-show-password-button",
            on_clicked=self._on_show_password_clicked,
        )

        self.show_password_label = Label(
            label="Show password", name="wifi-dialog-show-password-label"
        )

        self.show_password_box = Box(
            orientation="h",
            spacing=8,
            children=[self.show_password_button, self.show_password_label],
            name="wifi-dialog-show-password-box",
        )

        self.cancel_button = Button(
            label="Cancel",
            name="wifi-dialog-cancel-button",
            on_clicked=self._on_cancel_clicked,
        )

        self.join_button = Button(
            label="Join",
            name="wifi-dialog-join-button",
            on_clicked=self._on_join_clicked,
        )

        self.button_box = Box(
            orientation="h",
            spacing=12,
            children=[self.cancel_button, self.join_button],
            name="wifi-dialog-button-box",
            h_align="end",
        )

        self.password_container = Box(
            orientation="v",
            spacing=6,
            children=[self.password_label, self.password_entry, self.show_password_box],
            name="wifi-dialog-password-container",
        )

        self.content_box = Box(
            orientation="v",
            spacing=12,
            children=[
                self.title_container,
                self.error_label,
                self.password_container,
                self.button_box,
            ],
            name="wifi-dialog-content",
            h_align="center",
            v_align="center",
        )

        self.dialog_background = Box(
            children=[self.content_box],
            name="wifi-dialog-background",
            h_align="center",
            v_align="center",
        )

        self.children = self.dialog_background

        self._update_join_button_state()

    def _on_password_changed(self, entry):
        self._update_join_button_state()

    def _update_join_button_state(self):
        password = self.password_entry.get_text().strip()
        has_password = len(password) > 0

        if has_password:
            self.join_button.set_opacity(1.0)
            self.join_button.remove_style_class("disabled")
        else:
            self.join_button.set_opacity(0.5)
            self.join_button.add_style_class("disabled")

    def _on_show_password_clicked(self, *args):
        self.password_visible = not self.password_visible
        self.password_entry.set_visibility(self.password_visible)

        icon_name = (
            "view-reveal-symbolic" if self.password_visible else "view-conceal-symbolic"
        )
        self.show_password_button.get_image().set_property("icon-name", icon_name)

    def _on_key_press(self, widget, event):
        keyval = event.keyval

        if keyval == Gdk.KEY_Return or keyval == Gdk.KEY_KP_Enter:
            self._on_join_clicked()
            return True
        elif keyval == Gdk.KEY_Escape:
            self._on_cancel_clicked()
            return True

        return False

    def _on_visibility_changed(self, widget, *args):
        """Handle visibility changes"""
        if self.get_visible():
            GLib.timeout_add(100, lambda: self.password_entry.grab_focus())

    def _on_cancel_clicked(self, *args):
        self.hide()
        if self.on_cancel_callback:
            self.on_cancel_callback()
        if self.on_dialog_closed:
            self.on_dialog_closed()

    def _on_join_clicked(self, *args):
        if self.is_connecting:
            return

        password = self.password_entry.get_text().strip()
        if not password:
            self.password_entry.grab_focus()
            return

        self.is_connecting = True
        self.join_button.set_sensitive(False)

        self.connection_timeout_id = GLib.timeout_add(5000, self._connection_timeout)
        self.error_label.set_visible(False)

        self.hide()
        if self.on_connect_callback:
            self.on_connect_callback(self.ssid, password)
        if self.on_dialog_closed:
            self.on_dialog_closed()

    def _connection_timeout(self):
        if self.is_connecting:
            self.is_connecting = False
            self.join_button.set_sensitive(True)
            self.show_error("Connection timeout. Please try again.")
        return False

    def show_dialog(self):
        if self.connection_timeout_id:
            GLib.source_remove(self.connection_timeout_id)
            self.connection_timeout_id = None

        self.show_all()
        self.password_entry.set_text("")
        self.error_label.set_visible(False)

        self.password_visible = False
        self.password_entry.set_visibility(False)
        self.show_password_button.get_image().set_property(
            "icon-name", "view-conceal-symbolic"
        )

        self.is_connecting = False
        self.join_button.set_sensitive(True)

        self._update_join_button_state()

    def show_error(self, message="Incorrect password. Please try again."):
        if self.connection_timeout_id:
            GLib.source_remove(self.connection_timeout_id)
            self.connection_timeout_id = None

        self.is_connecting = False
        self.join_button.set_sensitive(True)

        if not self.get_visible():
            self.error_label.set_text(message)
            self.error_label.set_visible(True)
            self.show_all()
            GLib.timeout_add(10, lambda: self._focus_and_select_password())
        else:
            self.error_label.set_text(message)
            self.error_label.set_visible(True)
            self._focus_and_select_password()

    def _focus_and_select_password(self):
        try:
            self.password_entry.grab_focus()
            self.password_entry.select_region(0, -1)
            return False
        except:
            return False

    def get_password(self):
        return self.password_entry.get_text()

    def destroy_dialog(self):
        self.hide()
        self.destroy()
