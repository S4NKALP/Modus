from collections.abc import Iterator
from typing import Dict, Any
from utils.wayland import WaylandWindow as Window
from fabric.widgets.box import Box
from fabric.widgets.entry import Entry
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from fabric.widgets.image import Image
from fabric.utils import get_relative_path,  remove_handler, idle_add, DesktopApp
from gi.repository import Gdk, GLib, Gtk

# Import plugins
from .plugins import LauncherPlugin
from .plugins.applications import ApplicationsPlugin
from .plugins.calculator import CalculatorPlugin
from .plugins.web_search import WebSearchPlugin
from .plugins.emoji import EmojiPlugin
from .plugins.cliphist import CliphistPlugin
from .plugins.powermenu import PowerMenuPlugin

class Launcher(Window):
    def __init__(self):
        super().__init__(
            name="launcher",
            layer="top",
            anchor="center",
            exclusivity="none",
            keyboard_mode="on-demand",
            visible=False,
            all_visible=False,
        )
        self._arranger_handler: int = 0
        self._selected_index = 0
        self._results = []
        self._active_category = None  # No active category by default
        
        # Initialize plugins
        self._plugins = [
            ApplicationsPlugin(),
            CalculatorPlugin(),
            WebSearchPlugin(),
            EmojiPlugin(),
            CliphistPlugin(),
            PowerMenuPlugin(),
        ]
        
        self.viewport = Box(orientation="v", spacing=2)

        self.search = Entry(
            placeholder="Search for apps, files, and more...",
            h_expand=True,
            name="launcher-search",
        )
        
        # Create the apps ScrolledWindow
        self.apps = ScrolledWindow(
            spacing=10,
            min_content_size=(450, 405),
            max_content_size=(450, 405),
            child=self.viewport,
            name="launcher-apps",
        )

        # Add components to the main window
        self.add(
            Box(
                orientation="v",
                spacing=8,
                children=[
                    self.search,  
                    self.apps
                ],
            )
        )
        
        self.show_all()
        self.hide()
        self.add_keybinding("Escape", lambda *_: self.close())

        # Set up the search callback after all UI components are created
        self.search.connect("notify::text", lambda entry, *_: self.arrange_viewport(entry.get_text()))

        # Set up Enter key handling for the search entry
        self.search.connect("key-press-event", self.on_search_key_press)

        # Initially hide the scrolled window until search begins
        self.apps.set_visible(False)
        

    def close(self):
        self.search.set_text("")
        self._selected_index = 0
        self.hide()

    def on_search_key_press(self, entry, event):
        """Handle key press events in the search entry"""
        # Check if Enter or Return key was pressed
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.execute_first_result()
            return True  # Event handled
        return False  # Let other handlers process the event

    def execute_first_result(self):
        """Execute the action of the first search result if available"""
        if self._results:
            first_result = self._results[0]
            # Execute the action, clear search, and hide launcher
            first_result["action"]()
            self.search.set_text("")
            self.hide()

    def _get_result_priority(self, result: Dict[str, Any], query: str) -> int:
        """Get priority score for result sorting (lower = higher priority)"""
        title = result.get("title", "").lower()
        query_lower = query.lower()

        # Priority 100: Generic web search (fallback option) - Check this FIRST
        if "search the web for" in title.lower():
            return 100

        # Priority 0: Clipboard results when searching for "clip" or "clipboard"
        if query_lower in ["clip", "clipboard"] and "clip_id" in result:
            return 0

        # Priority 1: Exact matches (applications, emojis with exact names)
        if title == query_lower:
            return 1

        # Priority 2: Starts with query (applications, emojis starting with query)
        if title.startswith(query_lower):
            return 2

        # Priority 3: Contains query (partial matches)
        if query_lower in title:
            return 3

        # Priority 4: Calculator results (specific functional results)
        if "=" in title and any(char.isdigit() for char in title):
            return 4

        # Priority 5: Emoji results (specific content matches)
        if "emoji_icon" in result:
            return 5

        # Priority 6: Application results (specific app matches)
        if "icon" in result and hasattr(result["icon"], "get_icon_pixbuf"):
            return 6

        # Priority 7: Clipboard results (when not directly searching for clipboard)
        if "clip_id" in result:
            return 7

        # Priority 8: Other results
        return 8

    def select_next_result(self):
        if not self._results:
            return
        
        self._selected_index = (self._selected_index + 1) % len(self._results)
        self.update_selection()

    def update_selection(self):
        # Remove focus from all buttons
        for i, child in enumerate(self.viewport.get_children()):
            if isinstance(child, Button):
                if i == self._selected_index:
                    child.grab_focus()
                else:
                    child.set_state_flags(0, True)

    def arrange_viewport(self, query: str = ""):
        remove_handler(self._arranger_handler) if self._arranger_handler else None
        self._selected_index = 0
        self.viewport.children = []
        self._results = []

        # Show or hide UI elements based on query
        has_query = bool(query)
        self.apps.set_visible(has_query)
        
        # Get results from all plugins
        for plugin in self._plugins:
            plugin_results = plugin.search(query)
            self._results.extend(plugin_results)

        # Sort results by relevance (prioritize specific matches over generic ones)
        self._results.sort(key=lambda result: self._get_result_priority(result, query))

        results_iter = iter(self._results)
        
        self._arranger_handler = idle_add(
            lambda *args: self.add_next_result(*args)
            or self.resize_viewport(),
            results_iter,
            pin=True,
        )
        
        # Make sure search entry maintains focus
        self.search.grab_focus()
        
        return False

    def update_action_area(self, query: str):
        self.action_area.children = []
        
        if not query:
            return
            
        # Get action items from all plugins
        action_items = []
        for plugin in self._plugins:
            action_items.extend(plugin.get_action_items(query))
            
        # Add action items to UI
        for item in action_items:
            action_box = Box(orientation="h", name="launcher-action")
            action_box.add(Image(icon_name=item["icon_name"], name="launcher-action-icon"))
            action_box.add(Label(label=item["title"], name="launcher-action-label"))
            
            # Wrap in a button for clickability
            action_button = Button(
                name="launcher-action-button",
                child=action_box,
                on_clicked=lambda _, item=item: (
                    item["action"](),
                    self.search.set_text(""),  # Clear search entry when action is executed
                    self.hide(),
                ),
            )
            
            self.action_area.add(action_button)
        
        self.action_area.show_all()

    def add_next_result(self, results_iter: Iterator[Dict[str, Any]]):
        if not (result := next(results_iter, None)):
            return False

        button = self.bake_result_slot(result)
        self.viewport.add(button)
        
        # Highlight the first result without stealing focus
        if self._selected_index == 0 and self.search.get_text():
            button.set_state_flags(Gtk.StateFlags.FOCUSED, True)
        
        return True

    def resize_viewport(self):
        self.apps.set_min_content_width(
            self.viewport.get_allocation().width  # type: ignore
        )
        return False

    def bake_result_slot(self, result: Dict[str, Any], **kwargs) -> Button:
        # Create a more spotlight-like result entry
        if "emoji_icon" in result:
            # Handle emoji icons - display emoji as text
            icon = Label(
                label=result["emoji_icon"],
                h_align="start",
                name="launcher-emoji-icon",
            )
            # Set font size for emoji display
            icon.build().set_markup(f'<span font_size="24000">{result["emoji_icon"]}</span>').unwrap()
        elif "icon_markup" in result:
            # Handle icon markup (e.g., power menu icons)
            icon = Label(
                markup=result["icon_markup"],
                h_align="start",
                name="launcher-power-icon",
            )
            # Set font size and family for icon display
            icon.build().set_markup(f'<span font_family="tabler-icons" font_size="32000">{result["icon_markup"]}</span>').unwrap()
        elif "image_pixbuf" in result:
            # Handle direct pixbuf images (e.g., clipboard images)
            icon = Image(
                pixbuf=result["image_pixbuf"],
                h_align="start",
                name="launcher-app-icon",
            )
        elif "icon" in result and isinstance(result["icon"], DesktopApp):
            # Handle DesktopApp icons
            icon = Image(
                pixbuf=result["icon"].get_icon_pixbuf(size=50),
                h_align="start",
                name="launcher-app-icon",
            )
        else:
            # Handle regular icon names
            icon = Image(
                icon_name=result.get("icon_name", "application-x-executable-symbolic"),
                h_align="start",
                name="launcher-app-icon",
            )
            icon.build().set_pixel_size(50).unwrap()
            
        result_box = Box(
            orientation="h",
            spacing=12,
            children=[
                icon,
                Box(
                    orientation="v",
                    spacing=2,
                    children=[
                        Label(
                            label=result["title"],
                            h_align="start",
                            name="launcher-app-title",
                        ),
                        Label(
                            label=result.get("description", ""),
                            h_align="start",
                            name="launcher-app-description",
                        ),
                    ]
                ),
            ],
        )
        
        button = Button(
            name="launcher-app",
            child=result_box,
            on_enter_notify_event=lambda *_: self.set_cursor("pointer"),
            on_clicked=lambda *_: (
                result["action"](),
                self.search.set_text(""),  # Clear search entry when item is opened
                self.hide(),
            ),
            **kwargs,
        )
        
        return button

