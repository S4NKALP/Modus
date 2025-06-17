"""
Main launcher window implementation.
Provides a search interface with plugin-based results.
"""

import gi
from typing import List, Optional
from fabric.widgets.window import Window
from fabric.widgets.box import Box
from fabric.widgets.entry import Entry
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.core.service import Property
from utils.wayland import WaylandWindow
from .plugin_manager import PluginManager
from .result_item import ResultItem
from .result import Result
from .trigger_config import TriggerConfig

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib


class Launcher(WaylandWindow):
    """
    Main launcher window with search functionality and plugin system.
    Similar to Albert Launcher interface.
    """
    
    # Properties
    query = Property(str, flags="read-write", default_value="")
    visible = Property(bool, flags="read-write", default_value=False)
    active_trigger = Property(str, flags="read-write", default_value="")
    
    def __init__(self, **kwargs):
        super().__init__(
            name="launcher-window",
            layer="overlay",
            anchor="center",
            exclusivity="auto",
            keyboard_mode="on-demand",
            **kwargs,
        )
        
        # Initialize plugin manager
        self.plugin_manager = PluginManager()

        # Initialize trigger configuration
        self.trigger_config = TriggerConfig()

        # Current results and selection
        self.results: List[Result] = []
        self.selected_index = 0
        self.max_results = 10

        # Trigger system
        self.triggered_plugin = None  # Currently active triggered plugin

        
        # Setup UI
        self._setup_ui()
        
        # Connect signals
        self.connect("key-press-event", self._on_key_press)

        
        # Initially hide
        self.hide()
        
    def _setup_ui(self):
        """Setup the launcher UI components."""
        # Main container
        main_box = Box(
            name="launcher-main",
            orientation="v",
            spacing=0,
            h_align="center",
            v_align="center",
        )
        self.add(main_box)
        
        # Search entry with overlay for trigger indication
        self.search_entry = Entry(
            name="launcher-search",
            placeholder="Type to search...",
            h_expand=True,
        )
        self.search_entry.connect("changed", self._on_search_changed)
        self.search_entry.connect("activate", self._on_entry_activate)
        main_box.add(self.search_entry)
        
        # Results container
        self.results_scroll = ScrolledWindow(
            name="launcher-results-scroll",
            h_scrollbar_policy="never",
            v_scrollbar_policy="automatic",
            min_content_size=(-1, 550),
            max_content_size=(-1, 550),
        )
        
        self.results_box = Box(
            name="launcher-results",
            orientation="v",
            spacing=0,
        )
        self.results_scroll.add(self.results_box)
        main_box.add(self.results_scroll)

        # Initially hide the results container
        self.results_scroll.hide()

        
    def show_launcher(self):
        """Show the launcher and focus the search entry."""
        self.show_all()
        # Show available triggers when first opened
        self._show_available_triggers()
        self.search_entry.grab_focus()
        self.visible = True
        
    def hide_launcher(self):
        """Hide the launcher and clear search."""
        self.hide()
        self.search_entry.set_text("")
        self._clear_results()
        self.triggered_plugin = None
        self.active_trigger = ""
        self.visible = False
        
    def _on_search_changed(self, entry):
        """Handle search text changes."""
        query = entry.get_text().strip()
        self.query = query

        if query:
            # Debounce search to avoid too many queries
            GLib.timeout_add(150, self._perform_search, query)
        else:
            # Show available triggers when query is empty
            self._show_available_triggers()
            
    def _perform_search(self, query: str) -> bool:
        """Perform search across all plugins."""
        # Only search if query hasn't changed
        if query != self.query:
            return False

        if not query:
            # Empty query - reset trigger mode and hide results
            self.triggered_plugin = None
            self.active_trigger = ""
            self._clear_results()
            return False

        # Check if we're already in trigger mode
        if self.triggered_plugin and self.active_trigger:
            # We're in trigger mode - search within the triggered plugin
            try:
                # Extract the search query after the trigger
                remaining_query = self._extract_query_after_trigger(query, self.active_trigger)
                all_results = self.triggered_plugin.query(remaining_query)
            except Exception as e:
                print(f"Error in triggered plugin {self.triggered_plugin.name}: {e}")
                all_results = []
        else:
            # Check for trigger activation
            triggered_plugin, trigger = self._detect_trigger(query)

            if triggered_plugin:
                # New trigger detected - enter trigger mode
                self.triggered_plugin = triggered_plugin
                self.active_trigger = trigger

                # Extract search query after trigger
                remaining_query = self._extract_query_after_trigger(query, trigger)

                if remaining_query:
                    # Search with remaining content
                    try:
                        all_results = triggered_plugin.query(remaining_query)
                    except Exception as e:
                        print(f"Error in triggered plugin {triggered_plugin.name}: {e}")
                        all_results = []
                else:
                    # Just trigger keyword - show empty results or trigger help
                    all_results = []
            else:
                # No trigger detected - try global search across all plugins
                self.triggered_plugin = None
                self.active_trigger = ""

                # First try trigger suggestions if query matches trigger prefixes
                trigger_suggestions = self._get_trigger_suggestions(query)

                if trigger_suggestions:
                    # Show trigger suggestions
                    all_results = trigger_suggestions
                else:
                    # No trigger suggestions - do global search across all plugins
                    all_results = self._global_search(query)

        # Sort results by relevance score
        all_results.sort(key=lambda r: r.relevance, reverse=True)

        # Check if any results have bypass_max_results flag
        has_bypass = any(
            hasattr(r, 'data') and r.data and r.data.get('bypass_max_results')
            for r in all_results
        )

        # Only limit results if no bypass flag is present
        if not has_bypass:
            self.results = all_results[:self.max_results]
        else:
            self.results = all_results
        self.selected_index = 0

        # Update UI
        self._update_results_display()

        return False  # Don't repeat timeout

    def _extract_query_after_trigger(self, query: str, trigger: str) -> str:
        """
        Extract the search query after removing the trigger.

        Args:
            query: The full query string
            trigger: The trigger keyword

        Returns:
            The remaining query after the trigger
        """
        if not query or not trigger:
            return ""

        query_lower = query.lower()
        trigger_lower = trigger.lower()

        # Handle trigger with space (e.g., "app ")
        if trigger_lower.endswith(' ') and query_lower.startswith(trigger_lower):
            return query[len(trigger):].strip()

        # Handle trigger without space (e.g., "app")
        trigger_word = trigger.strip().lower()
        if query_lower.startswith(trigger_word):
            # Check if it's followed by space or end of string
            if len(query) == len(trigger_word):
                return ""
            elif len(query) > len(trigger_word) and query[len(trigger_word)] == ' ':
                return query[len(trigger_word) + 1:].strip()
            elif len(query) > len(trigger_word):
                # No space after trigger word, extract rest
                return query[len(trigger_word):].strip()

        return ""

    def _global_search(self, query: str):
        """
        Perform global search across all plugins.

        Args:
            query: The search query

        Returns:
            List of Result objects from all plugins
        """
        all_results = []

        # Search in all active plugins
        for plugin in self.plugin_manager.get_active_plugins():
            try:
                plugin_results = plugin.query(query)
                all_results.extend(plugin_results)
            except Exception as e:
                print(f"Error searching in plugin {plugin.name}: {e}")

        return all_results

    def _show_available_triggers(self):
        """Show available triggers when launcher is first opened."""
        trigger_suggestions = self._get_trigger_suggestions("")
        self.results = trigger_suggestions[:self.max_results]
        self.selected_index = 0
        self._update_results_display()

    def _detect_trigger(self, query: str):
        """
        Detect if query starts with a trigger keyword.

        Args:
            query: The search query

        Returns:
            Tuple of (plugin, trigger) if triggered, (None, "") otherwise
        """
        if not query.strip():
            return None, ""

        # Check all plugins for triggers
        for plugin in self.plugin_manager.get_active_plugins():
            trigger = plugin.get_active_trigger(query)
            if trigger:
                return plugin, trigger

        return None, ""

    def _get_trigger_suggestions(self, query: str):
        """
        Get trigger suggestions based on the current query.

        Args:
            query: The search query

        Returns:
            List of Result objects showing available triggers
        """
        from .result import Result

        suggestions = []
        query_lower = query.lower().strip()

        # Get all available triggers from plugins
        all_triggers = {}
        for plugin in self.plugin_manager.get_active_plugins():
            triggers = plugin.get_triggers()
            for trigger in triggers:
                trigger_clean = trigger.strip()
                if trigger_clean not in all_triggers:
                    all_triggers[trigger_clean] = {
                        'plugin': plugin,
                        'trigger': trigger,
                        'examples': []
                    }

        # Get max examples to show from configuration
        max_examples = self.trigger_config.get_max_examples_shown()

        # Show trigger suggestions based on query
        if query_lower:
            # Show triggers that match the query
            for trigger_clean, info in all_triggers.items():
                if trigger_clean.lower().startswith(query_lower):
                    examples = self.trigger_config.get_trigger_examples(trigger_clean)
                    icon_name = self.trigger_config.get_trigger_icon(trigger_clean)
                    description = self.trigger_config.get_trigger_description(trigger_clean)

                    # Create result for this trigger
                    result = Result(
                        title=f"{trigger_clean}",
                        subtitle=f"{description} - {', '.join(examples[:max_examples])}",
                        icon_markup=icon_name,
                        action=lambda t=trigger_clean: self._activate_trigger(t),
                        relevance=100 - len(trigger_clean),  # Shorter triggers get higher relevance
                        data={"type": "trigger_suggestion", "trigger": trigger_clean}
                    )
                    suggestions.append(result)
        else:
            # Empty query - show all available triggers
            for trigger_clean, info in all_triggers.items():
                examples = self.trigger_config.get_trigger_examples(trigger_clean)
                icon_name = self.trigger_config.get_trigger_icon(trigger_clean)
                description = self.trigger_config.get_trigger_description(trigger_clean)

                # Create result for this trigger
                result = Result(
                    title=f"{trigger_clean}",
                    subtitle=f"{description} - {', '.join(examples[:max_examples])}",
                    icon_markup=icon_name,
                    action=lambda t=trigger_clean: self._activate_trigger(t),
                    relevance=100 - len(trigger_clean),  # Shorter triggers get higher relevance
                    data={"type": "trigger_suggestion", "trigger": trigger_clean}
                )
                suggestions.append(result)

        return suggestions[:self.max_results]

    def _activate_trigger(self, trigger: str):
        """
        Activate a trigger by setting it in the search entry.

        Args:
            trigger: The trigger keyword to activate
        """
        # Set the trigger text in the search entry
        trigger_text = f"{trigger} "
        self.search_entry.set_text(trigger_text)
        self.search_entry.set_position(-1)  # Move cursor to end

        # Manually set the trigger mode to avoid search processing issues
        triggered_plugin, detected_trigger = self._detect_trigger(trigger_text)
        if triggered_plugin:
            self.triggered_plugin = triggered_plugin
            self.active_trigger = detected_trigger

            # Clear results and show trigger ready state
            self.results = []
            self.selected_index = 0
            self._update_results_display()

        # Focus back to the search entry for immediate typing
        self.search_entry.grab_focus()

        # Don't hide the launcher - user should be able to continue typing

    def _update_results_display(self):
        """Update the results display."""
        # Update input field with trigger indication (Albert-style)
        self._update_input_action_text()

        # Clear existing results
        for child in self.results_box.get_children():
            self.results_box.remove(child)

        # Add new results
        for i, result in enumerate(self.results):
            result_item = ResultItem(
                result=result,
                selected=(i == self.selected_index)
            )
            result_item.clicked.connect(lambda _, idx=i: self._on_result_clicked(result_item, idx))
            self.results_box.add(result_item)

        self.results_box.show_all()

        # Show/hide scroll container based on results
        if self.results:
            self.results_scroll.show()
        else:
            self.results_scroll.hide()

    def _update_input_action_text(self):
        """Update the input field with action text (Albert-style)."""
        # Get the current input text
        current_text = self.search_entry.get_text()

        if self.triggered_plugin:
            if self.results:
                # Show the first result as action text
                first_result = self.results[0]
                action_text = first_result.title

                # For calculator results, show the evaluation
                if hasattr(first_result, 'data') and 'result' in first_result.data:
                    action_text = str(first_result.data['result'])

                # Set placeholder to show the action text
                if action_text and action_text != current_text:
                    self.search_entry.set_placeholder_text(f"{current_text} → {action_text}")
                else:
                    self.search_entry.set_placeholder_text(f"[{self.active_trigger.strip()}] searching...")
            else:
                # In trigger mode but no results yet
                if current_text == self.active_trigger.strip():
                    # Just the trigger keyword
                    self.search_entry.set_placeholder_text(f"[{self.active_trigger.strip()}] ready - type to search")
                else:
                    # Searching within trigger
                    self.search_entry.set_placeholder_text(f"[{self.active_trigger.strip()}] searching...")
        else:
            # Not in trigger mode - show trigger help
            if current_text:
                self.search_entry.set_placeholder_text("Type trigger keyword (calc, app, file, system...)")
            else:
                self.search_entry.set_placeholder_text("Type trigger keyword: calc, app, file, system...")
            
    def _clear_results(self):
        """Clear all results."""
        self.results = []
        self.selected_index = 0
        for child in self.results_box.get_children():
            self.results_box.remove(child)
        self.results_scroll.hide()
        
    def _on_key_press(self, widget, event):
        """Handle key press events."""
        keyval = event.keyval
        
        # Escape - exit trigger mode or hide launcher
        if keyval == Gdk.KEY_Escape:
            if self.triggered_plugin:
                # Exit trigger mode
                self.triggered_plugin = None
                self.active_trigger = ""
                self.search_entry.set_text("")
                self._clear_results()
                return True
            else:
                # Hide launcher
                self.hide_launcher()
                return True
            
        # Up/Down - navigate results
        if keyval == Gdk.KEY_Up:
            if self.results:
                self.selected_index = (self.selected_index - 1) % len(self.results)
                self._update_selection()
            return True
            
        if keyval == Gdk.KEY_Down:
            if self.results:
                self.selected_index = (self.selected_index + 1) % len(self.results)
                self._update_selection()
            return True
            
        # Enter - activate selected result
        if keyval == Gdk.KEY_Return:
            # Check for Shift+Enter to pin application
            if event.state & Gdk.ModifierType.SHIFT_MASK:
                if self.results and 0 <= self.selected_index < len(self.results):
                    result = self.results[self.selected_index]
                    if result.data and result.data.get("pin_action"):
                        result.data["pin_action"]()
                        return True
            # Normal Enter behavior
            self._activate_selected()
            return True
            
        # Tab - cycle through results
        if keyval == Gdk.KEY_Tab:
            if self.results:
                self.selected_index = (self.selected_index + 1) % len(self.results)
                self._update_selection()
            return True

        return False
        
    def _on_entry_activate(self, entry):
        """Handle entry activation (Enter key)."""
        self._activate_selected()
        
    def _on_result_clicked(self, result_item, index):
        """Handle result item click."""
        self.selected_index = index
        self._activate_selected()
        
  

    def _is_mouse_over_results(self):
        """Check if mouse is over the results area."""
        # Simple check - if we have results visible, assume user might be interacting
        return len(self.results) > 0 and self.results_scroll.get_visible()

        
    def _update_selection(self):
        """Update the visual selection of results."""
        children = self.results_box.get_children()
        selected_widget = None

        for i, child in enumerate(children):
            if isinstance(child, ResultItem):
                is_selected = (i == self.selected_index)
                child.set_selected(is_selected)
                if is_selected:
                    selected_widget = child

        # Scroll to make the selected item visible
        if selected_widget and self.results_scroll.get_visible():
            # Use immediate scrolling for better responsiveness
            self._scroll_to_widget(selected_widget)
            # Also schedule a more accurate scroll after layout is complete
            GLib.idle_add(self._ensure_selected_visible)

    def _scroll_to_widget(self, widget):
        """Scroll the results container to make the widget visible."""
        if not widget or not self.results_scroll.get_visible():
            return

        # Debug output (can be removed in production)
        # print(f"Scrolling to selected index: {self.selected_index}")

        # Get the scrolled window's vertical adjustment
        vadjustment = self.results_scroll.get_vadjustment()
        if not vadjustment:
            return

        # Use a simpler approach: scroll to the selected item index
        if self.results and 0 <= self.selected_index < len(self.results):
            # Get all children to work with actual widgets
            children = self.results_box.get_children()
            if not children or self.selected_index >= len(children):
                return

            # Get the selected child widget
            selected_child = children[self.selected_index]

            # Try to get actual allocation, fallback to estimation
            try:
                allocation = selected_child.get_allocation()
                item_height = allocation.height if allocation.height > 0 else 60
                item_y = allocation.y
            except:
                # Fallback to estimation
                item_height = 60  # Default item height
                item_y = self.selected_index * item_height

            # Get current scroll info
            current_scroll = vadjustment.get_value()
            page_size = vadjustment.get_page_size()
            max_scroll = vadjustment.get_upper() - page_size

            # Calculate visible area
            visible_top = current_scroll
            visible_bottom = current_scroll + page_size

            # Check if selected item is visible
            item_top = item_y
            item_bottom = item_y + item_height

            # Add some padding for better visibility
            padding = 10

            # Scroll if needed
            if item_top < visible_top + padding:
                # Item is above visible area - scroll up
                new_scroll = max(0, item_top - padding)
                vadjustment.set_value(new_scroll)
            elif item_bottom > visible_bottom - padding:
                # Item is below visible area - scroll down
                new_scroll = min(max_scroll, item_bottom - page_size + padding)
                vadjustment.set_value(new_scroll)

    def _ensure_selected_visible(self):
        """Alternative method to ensure selected item is visible using GTK methods."""
        if not self.results or self.selected_index < 0 or self.selected_index >= len(self.results):
            return False

        children = self.results_box.get_children()
        if self.selected_index < len(children):
            selected_child = children[self.selected_index]

            # Try to use widget's allocation for more accurate scrolling
            try:
                allocation = selected_child.get_allocation()
                if allocation.height > 0:
                    vadjustment = self.results_scroll.get_vadjustment()
                    if vadjustment:
                        # Calculate the position to center the selected item
                        page_size = vadjustment.get_page_size()
                        target_pos = allocation.y - (page_size / 2) + (allocation.height / 2)
                        target_pos = max(0, min(target_pos, vadjustment.get_upper() - page_size))
                        vadjustment.set_value(target_pos)
            except Exception as e:
                print(f"Error in _ensure_selected_visible: {e}")

        return False  # Don't repeat the idle callback

    def _activate_selected(self):
        """Activate the currently selected result."""
        if self.results and 0 <= self.selected_index < len(self.results):
            result = self.results[self.selected_index]
            try:
                # Check if this is a trigger suggestion
                is_trigger_suggestion = (
                    result.data and
                    result.data.get("type") == "trigger_suggestion"
                )

                # Activate the result
                result.activate()

                # Only hide launcher for non-trigger suggestions
                if not is_trigger_suggestion:
                    self.hide_launcher()
                # For trigger suggestions, the launcher stays open and
                # the user can continue typing after the trigger

            except Exception as e:
                print(f"Error activating result: {e}")
