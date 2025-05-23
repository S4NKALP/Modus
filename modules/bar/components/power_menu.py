from fabric.widgets.button import Button
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.stack import Stack
from fabric.widgets.revealer import Revealer
from fabric.utils import exec_shell_command_async
from gi.repository import GLib, Gdk, Gtk
import utils.icons as icons


class Power(Button):
    TRANSITION_TYPE = "slide-up-down"
    TRANSITION_DURATION = 300  # milliseconds
    LABEL_TRANSITION_TYPE = "slide-left"
    LONG_PRESS_DURATION = 500  # milliseconds
    SCROLL_COOLDOWN = 100  # milliseconds

    def __init__(self):
        self.current_action = "shutdown"
        self.is_locked = True
        self.long_press_timeout = None
        self.scroll_timeout = None
        self.just_unlocked = False

        # Initialize stacks for icons and labels
        for name in ["icon_stack", "label_stack"]:
            setattr(
                self,
                name,
                Stack(
                    transition_type=self.TRANSITION_TYPE,
                    transition_duration=self.TRANSITION_DURATION,
                ),
            )

        # Define power actions
        self.power_actions = {
            "shutdown": {
                "icon": icons.shutdown,
                "label": "Shutdown",
                "command": "systemctl poweroff"
            },
            "reboot": {
                "icon": icons.reboot,
                "label": "Reboot",
                "command": "systemctl reboot"
            },
            "suspend": {
                "icon": icons.suspend,
                "label": "Suspend",
                "command": "systemctl suspend"
            },
            "logout": {
                "icon": icons.logout,
                "label": "Logout",
                "command": "hyprctl dispatch exit"
            },
            "lock": {
                "icon": icons.lock,
                "label": "Lock",
                "command": "hyprlock --immediate"
            }
        }

        # Add all actions to stacks
        for action, data in self.power_actions.items():
            self.icon_stack.add_named(
                Label(
                    markup=data["icon"],
                    style_classes="powericon",
                ),
                name=action,
            )
            self.label_stack.add_named(
                Label(
                    label=data["label"],
                    style_classes="powerlabel"
                ),
                name=action,
            )

        self.revealer = Revealer(
            transition_type=self.LABEL_TRANSITION_TYPE,
            transition_duration=self.TRANSITION_DURATION,
            child=self.label_stack,
        )

        super().__init__(
            name="power-menu",
            on_enter_notify_event=lambda *args: self.revealer.set_reveal_child(True),
            on_leave_notify_event=self.on_leave,
            on_pressed=self.on_pressed,
            on_released=self.on_released,
            on_scroll_event=self.on_scroll,
            child=Box(
                children=[
                    self.icon_stack,
                    self.revealer,
                ]
            ),
        )

        self.add_events(
            Gdk.EventMask.SCROLL_MASK |
            Gdk.EventMask.BUTTON_PRESS_MASK |
            Gdk.EventMask.SMOOTH_SCROLL_MASK
        )
        self.add_style_class("locked")
        
        # Add cursor change on hover
        self.connect(
            "state-flags-changed",
            lambda btn, *_: (
                btn.set_cursor("pointer")
                if btn.get_state_flags() & Gtk.StateFlags.PRELIGHT  # type: ignore
                else btn.set_cursor("default"),
            ),
        )

    def on_pressed(self, widget, event=None):
        if self.is_locked:
            self.long_press_timeout = GLib.timeout_add(
                self.LONG_PRESS_DURATION,
                self.on_long_press
            )

    def on_released(self, widget, event=None):
        timeout = self.long_press_timeout
        self.long_press_timeout = None
        if timeout:
            GLib.source_remove(timeout)
        
        if not self.is_locked and not self.just_unlocked:
            exec_shell_command_async(self.power_actions[self.current_action]["command"])
            self.is_locked = True
            self.add_style_class("locked")
        
        self.just_unlocked = False

    def on_long_press(self):
        if self.is_locked:
            self.is_locked = False
            self.just_unlocked = True
            self.remove_style_class("locked")
        self.long_press_timeout = None
        return False

    def _change_action(self, direction):
        if self.is_locked:
            return

        actions = list(self.power_actions.keys())
        current_index = actions.index(self.current_action)
        new_index = (current_index + direction) % len(actions)
        
        self.current_action = actions[new_index]
        self.icon_stack.set_visible_child_name(self.current_action)
        self.label_stack.set_visible_child_name(self.current_action)

    def on_scroll(self, widget, event):
        if self.is_locked:
            return True

        if event.direction == Gdk.ScrollDirection.SMOOTH:
            if event.delta_y < -0.1:
                self._change_action(-1)
            elif event.delta_y > 0.1:
                self._change_action(1)
        elif event.direction == Gdk.ScrollDirection.UP:
            self._change_action(-1)
        elif event.direction == Gdk.ScrollDirection.DOWN:
            self._change_action(1)

        self.scroll_timeout = GLib.timeout_add(self.SCROLL_COOLDOWN, lambda: None)
        return True
    def on_leave(self, widget, event=None):
        self.revealer.set_reveal_child(False)
        if not self.is_locked:
            self.is_locked = True
            self.add_style_class("locked")
