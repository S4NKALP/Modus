"""
Dashboard Tile Components

This module provides tile widgets for the dashboard interface.

Overview:
- Tiles are interactive components that display an icon, label, and status
- When clicked, tiles show their detailed content in the dashboard's content area
- Tiles can switch between mini (compact) and maxi (full) views
- Two tile types are available: Tile (standard) and TileSpecial (custom layouts)

Architecture:
- Tile: Standard tile with icon, label, properties, and optional menu button
- TileSpecial: Custom tile that can switch between different view layouts
- Both tiles communicate with the parent dashboard to show content

Usage:
- Create tiles with appropriate properties and add them to the dashboard
- The dashboard handles content switching and tile state management
- Tiles automatically notify the dashboard when clicked
"""

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from fabric.widgets.stack import Stack
from fabric.widgets.revealer import Revealer
import utils.icons as icons


class Tile(Box):
    """
    A dashboard tile widget that displays an icon, label, and properties.

    When clicked, the tile notifies the dashboard to show its detailed content
    in the dashboard's content area instead of expanding inline.

    Args:
        menu (bool): Whether this tile has a menu button
        markup (str): Icon markup to display
        label (str): Text label for the tile
        props (Label): Properties widget to show tile status
        **kwargs: Additional widget arguments
    """

    def __init__(self, *, menu: bool, markup: str, label: str, props: Label, **kwargs):
        # Setup CSS classes
        default_classes = ["tile"]
        extra_classes = kwargs.pop("style_classes", [])
        all_classes = default_classes + extra_classes

        super().__init__(style_classes=all_classes, v_align="start", **kwargs)

        # Store tile properties
        self.props = props
        self.toggle = False  # Track if tile is active
        self.dashboard_instance = None  # Reference to parent dashboard

        # Create tile components
        self._create_tile_icon(markup)
        self._create_tile_content(label)
        self._create_tile_layout(menu)

    def _create_tile_icon(self, markup: str):
        """Create the tile's icon label."""
        self.icon = Label(
            style_classes="tile-icon",
            markup=markup
        )

    def _create_tile_content(self, label: str):
        """Create the tile's text content area."""
        self.tile_label = Label(
            style_classes="tile-label",
            label=label,
            h_align="start"
        )

        # Container for label and properties
        self.type_box = Box(
            style_classes="tile-type",
            orientation="v",
            v_expand=True,
            h_expand=True,
            v_align="center",
            children=[self.tile_label, self.props],
        )

    def _create_tile_layout(self, has_menu: bool):
        """Create the tile's layout structure."""
        # Create menu button if needed
        if has_menu:
            self.menu_button = Button(
                style_classes="tile-button",
                h_expand=True,
                child=Label(style_classes="tile-icon", markup=icons.arrow_head),
                on_clicked=self.handle_click,
            )
            content_children = [self.type_box, self.menu_button]
        else:
            content_children = [self.type_box]

        # Create revealer for smooth transitions
        self.content_button = Revealer(
            transition_duration=150,
            transition_type="slide-left",
            h_expand=True,
            child=Box(children=content_children),
            child_revealed=True,
        )

        # Create the main tile view
        self.normal_view = Box(children=[self.icon, self.content_button])

        # Create placeholder menu (content is shown in dashboard content area)
        self.menu = Box(
            style_classes="tile-menu",
            children=[Label(label="Tile content will be shown in dashboard content area")],
        )

        # Stack to switch between normal and menu views
        self.stack = Stack(
            transition_type="crossfade",
            transition_duration=150,
            h_expand=True,
            children=[self.normal_view, self.menu],
        )

        self.children = self.stack

    def handle_click(self, *_):
        """
        Handle tile click events.

        When clicked, the tile toggles its active state and notifies the dashboard
        to show/hide its content in the dashboard's content area.
        """
        self.toggle = not self.toggle
        print(f"Tile {self.get_name()} clicked, toggle: {self.toggle}")

        # Notify dashboard to handle content switching
        if self.dashboard_instance:
            self.dashboard_instance.handle_tile_menu_expand(self.get_name(), self.toggle)

    def mini_view(self):
        """
        Switch tile to mini (compact) view.

        In mini view, the tile content is hidden and only the icon is shown.
        This is used when other tiles are active.
        """
        self.content_button.set_reveal_child(False)
        self.icon.set_h_expand(True)
        self.content_button.set_h_expand(False)
        self.add_style_class("mini")

    def maxi_view(self):
        """
        Switch tile to maxi (full) view.

        In maxi view, the tile shows its full content including label and properties.
        This is the default state when no tiles are active.
        """
        self.content_button.set_reveal_child(True)
        self.icon.set_h_expand(False)
        self.content_button.set_h_expand(True)
        self.remove_style_class("mini")


class TileSpecial(Box):
    """
    A special tile widget that can switch between normal and mini views.

    This tile type is used for components that need different layouts
    in normal vs compact modes (e.g., media player).

    Args:
        mini_props: Widget(s) to show in mini view
        props: Widget(s) to show in normal view
        **kwargs: Additional widget arguments
    """

    def __init__(self, *, mini_props, props, **kwargs):
        super().__init__(**kwargs)

        # Store view components
        self.props = props
        self.mini_props = mini_props
        self.toggle = False

        # Create view containers
        self._create_views()
        self._setup_layout()

    def _create_views(self):
        """Create the normal and collapsed view containers."""
        self.normal_view = Box(children=self.props)
        self.collapsed_view = Box(children=self.mini_props)

    def _setup_layout(self):
        """Setup the stack layout for switching between views."""
        self.stack = Stack(
            transition_type="crossfade",
            transition_duration=150,
            h_expand=True,
            v_align="start",
            children=[self.normal_view, self.collapsed_view],
        )
        self.children = self.stack

    def mini_view(self):
        """
        Switch to mini (collapsed) view.

        Hides the normal view and shows the compact mini view.
        Uses negative margins to hide the normal view completely.
        """
        self.normal_view.set_style("margin:-999px")
        self.collapsed_view.set_style("margin:0px;")
        self.stack.set_visible_child(self.collapsed_view)

    def maxi_view(self):
        """
        Switch to maxi (normal) view.

        Hides the mini view and shows the full normal view.
        Uses negative margins to hide the collapsed view completely.
        """
        self.collapsed_view.set_style("margin:-999px")
        self.normal_view.set_style("margin:0px;")
        self.stack.set_visible_child(self.normal_view)
