"""
UI component for displaying search results.
"""

from gi.repository import Gtk
import gi
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.image import Image
from fabric.widgets.eventbox import EventBox
from fabric.core.service import Signal
from modules.launcher.result import Result

gi.require_version("Gtk", "3.0")


class ResultItem(EventBox):
    """
    Widget for displaying a single search result.
    """

    # Signals
    @Signal
    def clicked(self, index: int) -> None:
        """Emitted when result is clicked."""
        pass

    def __init__(self, result: Result, selected: bool = False, **kwargs):
        super().__init__(name="launcher-result-item", **kwargs)

        self.result = result
        self._selected = selected

        # Setup UI
        self._setup_ui()

        # Connect signals
        self.connect("button-press-event", self._on_button_press)
        self.connect("enter-notify-event", self._on_enter)

        # Set initial selection state
        self.set_selected(selected)

    def _setup_ui(self):
        """Setup the result item UI."""
        # Main container
        main_box = Box(
            name="result-item-main",
            orientation="h",
            spacing=12,
            h_align="fill",
            v_align="center",
        )
        self.add(main_box)

        # Icon
        if self.result.icon:
            icon_widget = Image(pixbuf=self.result.icon, name="result-item-icon")
        elif self.result.icon_name:
            icon_widget = Image(
                icon_name=self.result.icon_name, icon_size=32, name="result-item-icon"
            )
        elif self.result.icon_markup:
            icon_widget = Label(
                markup=self.result.icon_markup, name="launcher-icon-label"
            )
        else:
            # Default icon
            icon_widget = Image(
                icon_name="application-x-executable",
                icon_size=32,
                name="result-item-icon",
            )

        main_box.add(icon_widget)

        # Text container
        text_box = Box(
            name="result-item-text",
            orientation="v",
            spacing=2,
            h_expand=True,
            v_align="center",
        )
        main_box.add(text_box)

        # Title
        title_label = Label(
            label=self.result.title,
            name="result-item-title",
            h_align="start",
            v_align="center",
            ellipsize="end",
        )
        text_box.add(title_label)

        # Subtitle (if present)
        if self.result.subtitle:
            subtitle_label = Label(
                label=self.result.subtitle,
                name="result-item-subtitle",
                h_align="start",
                v_align="center",
                ellipsize="end",
            )
            text_box.add(subtitle_label)

        # Plugin name (small text)
        if self.result.plugin_name:
            plugin_label = Label(
                label=f"via {self.result.plugin_name}",
                name="result-item-plugin",
                h_align="start",
                v_align="center",
                ellipsize="end",
            )
            text_box.add(plugin_label)

    def set_selected(self, selected: bool):
        """Set the selection state of this result item."""
        self._selected = selected

        if selected:
            self.add_style_class("selected")
        else:
            self.remove_style_class("selected")

    def get_selected(self) -> bool:
        """Get the selection state of this result item."""
        return self._selected

    def _on_button_press(self, widget, event):
        """Handle button press events."""
        if event.button == 1:  # Left click
            self.clicked.emit(0)  # Emit with dummy index, parent will handle
            return True
        return False

    def _on_enter(self, widget, event):
        """Handle mouse enter events."""
        # Could be used for hover effects
        return False
