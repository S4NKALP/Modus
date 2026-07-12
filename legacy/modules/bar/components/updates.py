import json
from fabric.utils import exec_shell_command_async, get_relative_path, invoke_repeater
from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.stack import Stack
from gi.repository import Gtk
import utils.icons as icons
import config.data as data


class UpdatesWidget(Button):
    """A widget to display the number of available updates."""

    def __init__(
        self,
        **kwargs,
    ):
        # Determine if we should use vertical layout for components
        is_vertical_layout = data.VERTICAL

        # Initialize the button with specific name and style
        super().__init__(
            name="update",
            orientation="h" if not is_vertical_layout else "v",
            **kwargs,
        )

        self.script_file = get_relative_path("../../../config/scripts/systemupdates.sh")

        self.update_level_label = Label(
            name="update-label",
            label="0",
            visible=False,  # Initially hidden
        )

        self.update_icon = Label(name="update-icon", markup=icons.update)
        self.updated_icon = Label(name="updated-icon", markup=icons.updated)

        # Create boxes with proper orientation
        self.update_box = CenterBox(
            orientation="v" if is_vertical_layout else "h",
            center_children=[self.update_icon, self.update_level_label],
        )

        self.updated_box = CenterBox(
            orientation="v" if is_vertical_layout else "h",
            center_children=[self.updated_icon],
        )

        # Stack to switch between states
        self.stack = Stack()
        self.stack.add_named(self.update_box, "update_box")
        self.stack.add_named(self.updated_box, "updated_box")
        self.stack.set_visible_child_name("update_box")

        self.children = Box(
            orientation="v" if is_vertical_layout else "h",
            children=self.stack,
        )

        # Configure stack transitions
        self.stack.set_homogeneous(False)
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)

        # Connect click handler
        self.connect("button-press-event", self.on_button_press)

        # Check for updates every minute
        invoke_repeater(60000, self.update, initial_call=True)

    def update_values(self, value: str) -> bool:
        """Update the widget state based on update check results"""
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return False

        update_count = str(value["total"])
        self.update_level_label.set_label(update_count)

        # Show appropriate state based on update count
        if update_count == "0":
            self.stack.set_visible_child_name("updated_box")
            self.update_level_label.set_visible(False)
        else:
            self.stack.set_visible_child_name("update_box")
            self.update_level_label.set_visible(True)

        self.set_tooltip_text(value.get("tooltip", ""))
        return True

    def on_button_press(self, _, event) -> bool:
        """Handle button press events"""
        if event.button == 1:  # Left click
            # Run update command
            exec_shell_command_async(
                f"{self.script_file} -arch -up",
                lambda _: None,
            )
            self.update()
            return True
        else:
            # Other clicks just refresh
            self.update()

    def update(self) -> bool:
        """Check for system updates"""
        exec_shell_command_async(
            f"{self.script_file} -arch",
            lambda output: self.update_values(output),
        )

        return True
