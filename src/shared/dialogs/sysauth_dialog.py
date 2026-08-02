"""Fabric-based authentication dialog for sysauth.

Provides a centered overlay password prompt matching the WiFi dialog pattern.
Uses Fabric widgets and integrates with the SysauthService for
Polkit authentication requests.
"""

import threading

from fabric.utils import Gdk, GLib
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.window import Window


class AuthDialog(Window):
    """Centered authentication dialog matching the WiFi password dialog pattern."""

    def __init__(self, action_id: str, message: str, icon_name: str):
        self._result_accepted = False
        self._main_loop = None
        self._dismissed = False

        super().__init__(
            title="modus-dialog",
            layer="overlay",
            anchor="center",
            keyboard_mode="on-demand",
            visible=False,
            name="sysauth-dialog",
        )

        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_keep_above(True)
        self.set_modal(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_resizable(False)

        self._action_id = action_id
        self._message = message
        self._icon_name = icon_name

        self._build_ui()
        self._connect_signals()

    def _build_ui(self):
        """Construct the dialog UI matching the WiFi dialog layout."""
        self._image = Image(
            icon_name=self._icon_name,
            size=48,
            name="sysauth-icon",
        )

        self._label_title = Label(
            label=self._action_id,
            name="sysauth-title",
            h_align="start",
            wrap=True,
            max_width_chars=40,
        )

        self._title_container = Box(
            orientation="h",
            spacing=8,
            children=[self._image, self._label_title],
            name="sysauth-title-container",
            h_align="start",
        )

        self._label_description = Label(
            label=self._message,
            name="sysauth-description",
            h_align="start",
            wrap=True,
            max_width_chars=40,
            lines=3,
        )

        self._error_label = Label(
            label="Incorrect password. Please try again.",
            name="sysauth-error",
            h_align="center",
            visible=False,
        )

        self._password_label = Label(
            label="Password:",
            name="sysauth-password-label",
            h_align="start",
        )

        self._entry_password = Entry(
            placeholder_text="Enter password",
            name="sysauth-password-entry",
            visibility=False,
            h_expand=True,
            h_align="fill",
        )

        self._password_container = Box(
            orientation="v",
            h_expand=True,
            spacing=6,
            children=[self._password_label, self._entry_password],
            name="sysauth-password-container",
        )

        self._button_cancel = Button(
            label="Cancel",
            name="sysauth-cancel-button",
            on_clicked=self._on_cancel_clicked,
        )

        self._button_ok = Button(
            label="Authenticate",
            name="sysauth-ok-button",
            on_clicked=self._on_ok_clicked,
        )

        self._button_box = Box(
            orientation="h",
            spacing=12,
            h_expand=True,
            children=[self._button_cancel, self._button_ok],
            name="sysauth-button-box",
            h_align="end",
        )

        self._content_box = Box(
            orientation="v",
            h_expand=True,
            spacing=12,
            children=[
                self._title_container,
                self._label_description,
                self._error_label,
                self._password_container,
                self._button_box,
            ],
            name="sysauth-content",
            h_align="fill",
            v_align="center",
        )

        self._dialog_background = Box(
            children=[self._content_box],
            name="sysauth-dialog-background",
            h_align="center",
            v_align="center",
        )

        self.children = self._dialog_background

    def _connect_signals(self):
        """Connect button and entry signals."""
        self._entry_password.connect("activate", lambda *_: self._on_ok_clicked())
        self.connect("key-press-event", self._on_key_press)
        self.connect("notify::visible", self._on_visibility_changed)

    def run(self) -> bool:
        """Show the dialog and run a nested main loop until dismissed.

        Returns:
            True if the user accepted (entered password), False if cancelled.
        """
        self._main_loop = GLib.MainLoop()

        self.show_all()
        self._error_label.set_visible(False)
        self._entry_password.grab_focus()

        if self._dismissed:
            return self._result_accepted

        self._main_loop.run()

        return self._result_accepted

    def _on_key_press(self, _widget, event):
        """Handle keyboard input."""
        keyval = event.keyval

        if keyval == Gdk.KEY_Return or keyval == Gdk.KEY_KP_Enter:
            self._on_ok_clicked()
            return True
        elif keyval == Gdk.KEY_Escape:
            self._on_cancel_clicked()
            return True

        return False

    def _on_visibility_changed(self, _widget, *_args):
        """Focus password entry when dialog becomes visible."""
        if self.get_visible():
            GLib.timeout_add(100, lambda: self._entry_password.grab_focus())

    def _on_ok_clicked(self, *_args):
        """Handle OK button press or Enter key."""
        password = self._entry_password.get_text().strip()
        if not password:
            self._entry_password.grab_focus()
            return

        self._result_accepted = True
        self._dismiss()

    def _on_cancel_clicked(self, *_args):
        """Handle Cancel button press or Escape key."""
        self._result_accepted = False
        self._dismiss()

    def _dismiss(self):
        """Dismiss the dialog."""
        self.hide()
        GLib.timeout_add(100, self._quit_main_loop)

    def dismiss(self):
        """Dismiss the dialog from any thread."""
        self._dismissed = True
        GLib.idle_add(self._dismiss)

    def _quit_main_loop(self):
        """Quit the nested main loop."""
        if self._main_loop is not None and self._main_loop.is_running():
            self._main_loop.quit()
        return False

    def show_error(self, message: str = "Incorrect password. Please try again."):
        """Show an error message in the dialog."""
        self._error_label.set_text(message)
        self._error_label.set_visible(True)
        self._entry_password.set_text("")
        GLib.timeout_add(10, lambda: self._entry_password.grab_focus())

    def reset(self):
        """Reset the dialog for reuse."""
        self._result_accepted = False
        self._dismissed = False
        self._error_label.set_visible(False)
        self._entry_password.set_text("")

    @property
    def password(self) -> str:
        """Get the entered password."""
        return self._entry_password.get_text()


def run_auth_dialog(
    action_id: str,
    message: str,
    icon_name: str,
    on_result=None,
    error_message: "str | None" = None,
):
    """Run an authentication dialog in a background thread.

    Args:
        action_id: The action identifier to display.
        message: Description of the action.
        icon_name: Icon name for the action.
        on_result: Callback(password: str | None) when dialog closes.
        error_message: Optional error message to show on first display.

    Returns:
        A callable that dismisses the dialog (thread-safe). Calling it
        before the dialog appears prevents the dialog from being shown.
    """
    state = {"dialog": None}

    def _dismiss():
        dialog = state.get("dialog")
        if dialog is not None:
            dialog.dismiss()
        else:
            state["cancelled"] = True

    def _run():
        dialog = AuthDialog(action_id, message, icon_name)
        state["dialog"] = dialog
        if state.get("cancelled"):
            return

        if error_message:
            GLib.idle_add(lambda: dialog.show_error(error_message))

        accepted = dialog.run()

        def _callback():
            if accepted and dialog.password:
                on_result(dialog.password)
            else:
                on_result(None)
            return False

        GLib.idle_add(_callback)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return _dismiss


def connect_sysauth_service(service):
    """Connect a SysauthService to the authentication dialog.

    Shows the dialog on ``begin-authentication``, responds on submit,
    re-prompts with an error on failed authentication, and dismisses
    the open dialog when polkitd cancels the request.

    Args:
        service: The SysauthService instance to wire up.
    """
    pending = {}
    open_dialogs = {}

    def _respond(cookie, password):
        threading.Thread(
            target=lambda: service.respond(cookie, password), daemon=True
        ).start()

    def _prompt(cookie, error_message=None):
        info = pending.get(cookie)
        if info is None:
            return
        action_id, message, icon_name = info

        def on_result(password):
            open_dialogs.pop(cookie, None)
            if password is None:
                pending.pop(cookie, None)
                service.cancel(cookie)
                return
            _respond(cookie, password)

        open_dialogs[cookie] = run_auth_dialog(
            action_id,
            message,
            icon_name,
            on_result=on_result,
            error_message=error_message,
        )

    def on_begin(_service, action_id, message, icon_name, cookie, _uid):
        pending[cookie] = (action_id, message, icon_name)
        _prompt(cookie)

    def on_cancelled(_service, cookie):
        pending.pop(cookie, None)
        dismiss = open_dialogs.pop(cookie, None)
        if dismiss is not None:
            dismiss()

    def on_completed(_service, cookie, success):
        if success:
            pending.pop(cookie, None)
            open_dialogs.pop(cookie, None)
        else:
            _prompt(cookie, error_message="Incorrect password. Please try again.")

    service.connect("begin-authentication", on_begin)
    service.connect("authentication-cancelled", on_cancelled)
    service.connect("authentication-completed", on_completed)
