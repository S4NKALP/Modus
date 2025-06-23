from typing import List, Optional, Tuple

import utils.icons as icons
from fabric.core.service import Property
from fabric.utils import exec_shell_command_async, get_relative_path
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow
from gi.repository import Gdk, GLib
from modules.launcher.plugin_manager import PluginManager
from modules.launcher.result import Result
from modules.launcher.result_item import ResultItem
from modules.launcher.trigger_config import TriggerConfig
from utils.wayland import WaylandWindow as Window

# Constants
SEARCH_DEBOUNCE_MS = 150
TRIGGER_SEARCH_DEBOUNCE_MS = 50
CURSOR_POSITION_DELAY_MS = 10
SCROLL_PADDING = 10
DEFAULT_ITEM_HEIGHT = 60
PAGE_NAVIGATION_STEP = 5
LAUNCHER_WIDTH = 550
LAUNCHER_HEIGHT = 260


class Launcher(Window):
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
            layer="top",
            anchor="center",
            exclusivity="none",
            keyboard_mode="exclusive",
            **kwargs,
        )

        # Initialization flag to prevent callbacks during setup
        self._initializing = True

        # Flag to prevent recursion when automatically adding spaces
        self._auto_adding_space = False

        # Flag to prevent search change handler interference during backspace processing
        self._processing_backspace = False

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
        self.active_trigger = ""  # Currently active trigger keyword
        self.query = ""  # Current search query
        self.visible = False  # Launcher visibility state
        self.opened_with_trigger = False  # Whether launcher was opened with a trigger

        # Focus management for header buttons
        self.focus_mode = "search"  # "search", "results", "header"
        self.header_button_index = 0  # 0 = config, 1 = close

        # Setup UI
        main_box = Box(
            name="launcher",
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
            h_align="fill",
            notify_text=lambda entry, *_: self._on_search_changed(entry),
        )
        self.search_entry.connect("changed", self._on_search_changed)
        self.search_entry.connect("activate", self._on_entry_activate)

        self.header_box = Box(
            name="header_box",
            spacing=10,
            orientation="h",
            children=[
                self.search_entry,
            ],
        )

        main_box.add(self.header_box)

        # Results container
        self.results_scroll = ScrolledWindow(
            name="launcher-results-scroll",
            h_scrollbar_policy="never",
            min_content_size=(LAUNCHER_WIDTH, LAUNCHER_HEIGHT),
            max_content_size=(LAUNCHER_WIDTH, LAUNCHER_HEIGHT),
            propagate_width=False,
            propagate_height=False,
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

        self.connect("key-press-event", self._on_key_press)
        self.hide()

        # Mark initialization as complete
        self._initializing = False

        # Hide trigger suggestions at startup
        self._clear_results()

    def show_launcher(self, trigger_keyword: str = None, external: bool = False):
        """Show the launcher and focus the search entry, or execute command externally.

        Args:
            trigger_keyword: Optional trigger keyword to activate immediately (e.g., "google", "calc", "app")
            external: If True, execute the command without showing the launcher UI
        """
        if external and trigger_keyword:
            # Execute command externally without showing launcher
            return self._execute_external_command(trigger_keyword)

        self.show_all()

        if trigger_keyword:
            # Set flag to track that launcher was opened with a trigger keyword
            self.opened_with_trigger = True

            # Set the trigger keyword with a space and activate trigger mode
            trigger_text = f"{trigger_keyword} "
            self.search_entry.set_text(trigger_text)

            # Detect and activate the trigger
            triggered_plugin, detected_trigger = self._detect_trigger(trigger_text)
            if triggered_plugin:
                self.triggered_plugin = triggered_plugin
                self.active_trigger = detected_trigger

                # Query the plugin with empty string to show default options
                try:
                    results = triggered_plugin.query("")
                    self.results = results
                    self.selected_index = 0
                    self._update_results_display()
                except Exception as e:
                    print(
                        f"Error querying triggered plugin {triggered_plugin.name}: {e}"
                    )
                    self._clear_results()
            else:
                # Trigger not found, clear and show error or fallback
                self.search_entry.set_text("")
                self._clear_results()
        else:
            # Normal launcher opening - clear everything
            self.opened_with_trigger = False
            self.search_entry.set_text("")
            self._clear_results()

        # Reset focus mode to search
        self.focus_mode = "search"
        self.header_button_index = 0

        # Remove focus styling from header buttons
        self._clear_header_focus()

        # Focus search entry without selecting text
        if trigger_keyword:
            # For trigger keywords, we want the cursor at the end
            self.search_entry.grab_focus()

            def position_cursor():
                if hasattr(self.search_entry, "set_position"):
                    self.search_entry.set_position(-1)  # Move caret to end
                return False  # Only run once

            GLib.idle_add(position_cursor)
        else:
            # For normal opening, use our method that prevents text selection
            self._focus_search_entry_without_selection()

        self.visible = True

    def _position_cursor_at_end(self, text_length: Optional[int] = None) -> None:
        """Position cursor at the end of search entry text."""
        if text_length is None:
            text_length = len(self.search_entry.get_text())

        def position_cursor():
            if hasattr(self.search_entry, "set_position"):
                self.search_entry.set_position(-1)  # Move caret to end
            if hasattr(self.search_entry, "select_region"):
                self.search_entry.select_region(
                    text_length, text_length
                )  # No selection
            return False  # Only run once

        GLib.idle_add(position_cursor)

    def _add_space_to_trigger(self, trigger_word: str) -> None:
        """Add space after trigger keyword and position cursor."""
        trigger_text_with_space = f"{trigger_word} "

        # Temporarily disable search change handling to prevent recursion
        self._auto_adding_space = True
        self.search_entry.set_text(trigger_text_with_space)

        # Position cursor at the end
        def position_cursor():
            if hasattr(self.search_entry, "set_position"):
                self.search_entry.set_position(-1)  # Move caret to end
            if hasattr(self.search_entry, "select_region"):
                self.search_entry.select_region(
                    len(trigger_text_with_space), len(trigger_text_with_space)
                )  # No selection
            self._auto_adding_space = False
            return False  # Only run once

        GLib.idle_add(position_cursor)

        # Update query
        self.query = trigger_text_with_space
        return trigger_text_with_space

    def close_launcher(self):
        """Hide the launcher and clear search."""
        self.hide()
        self.search_entry.set_text("")
        self._clear_results()
        self.triggered_plugin = None
        self.active_trigger = ""
        self.visible = False
        self.opened_with_trigger = False

    def _on_search_changed(self, entry):
        """Handle search text changes."""
        # Skip if still initializing
        if getattr(self, "_initializing", True):
            return

        # Skip if we're automatically adding a space to prevent recursion
        if getattr(self, "_auto_adding_space", False):
            return

        # Skip if we're processing a backspace to prevent interference
        if getattr(self, "_processing_backspace", False):
            return

        # Reset focus to search when user types
        if self.focus_mode != "search":
            self.focus_mode = "search"
            self._clear_header_focus()

        query = entry.get_text().strip()
        self.query = query

        # If query is exactly ':', show all triggers
        if query == ":":
            self._show_available_triggers()
        # If query matches a trigger exactly (with or without space), handle trigger activation
        elif any(
            query == trig or query == f"{trig} "
            for trig in [
                t.strip()
                for p in self.plugin_manager.get_active_plugins()
                for t in p.get_triggers()
            ]
        ):
            # Check if we need to add space immediately for exact trigger matches
            if not query.endswith(" "):
                # This is an exact trigger match without space - add space immediately
                trigger_text_with_space = self._add_space_to_trigger(query)
                GLib.timeout_add(
                    TRIGGER_SEARCH_DEBOUNCE_MS,
                    self._perform_search,
                    trigger_text_with_space,
                )
            else:
                # Already has space, proceed with normal search
                GLib.timeout_add(SEARCH_DEBOUNCE_MS, self._perform_search, query)
        elif query:
            # Debounce search to avoid too many queries
            GLib.timeout_add(SEARCH_DEBOUNCE_MS, self._perform_search, query)
        else:
            # Hide results when query is empty
            self._clear_results()

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
                remaining_query = self._extract_query_after_trigger(
                    query, self.active_trigger
                )
                all_results = self.triggered_plugin.query(remaining_query)
            except Exception as e:
                print(f"Error in triggered plugin {self.triggered_plugin.name}: {e}")
                all_results = []
        else:
            # Check for trigger activation
            triggered_plugin, trigger = self._detect_trigger(query)

            if triggered_plugin:
                # New trigger detected - check if we need to add space automatically
                trigger_word = trigger.strip()
                current_text = self.search_entry.get_text()

                # If the current text is exactly the trigger word (no space), add space automatically
                if (
                    current_text.strip() == trigger_word
                    and not current_text.endswith(" ")
                    and not getattr(self, "_auto_adding_space", False)
                ):
                    query = self._add_space_to_trigger(trigger_word)

                # Enter trigger mode
                self.triggered_plugin = triggered_plugin
                self.active_trigger = trigger

                # Extract search query after trigger
                remaining_query = self._extract_query_after_trigger(query, trigger)

                # Always call the plugin's query method, even with empty remaining query
                # This allows plugins to show default options when just the trigger is typed
                try:
                    all_results = triggered_plugin.query(remaining_query)
                except Exception as e:
                    print(f"Error in triggered plugin {triggered_plugin.name}: {e}")
                    all_results = []
            else:
                # No trigger detected - only show trigger suggestions
                self.triggered_plugin = None
                self.active_trigger = ""

                # Show trigger suggestions if query matches trigger prefixes
                trigger_suggestions = self._get_trigger_suggestions(query)
                all_results = trigger_suggestions

        # Sort results by relevance score
        all_results.sort(key=lambda r: r.relevance, reverse=True)

        # Check if any results have bypass_max_results flag
        has_bypass = any(
            hasattr(r, "data") and r.data and r.data.get("bypass_max_results")
            for r in all_results
        )

        # Don't limit results for triggered plugin queries, only for global searches and trigger suggestions
        if self.triggered_plugin and self.active_trigger:
            # In trigger mode - show all results from the triggered plugin
            self.results = all_results
        elif not has_bypass:
            # Global search or trigger suggestions - apply max_results limit
            self.results = all_results[: self.max_results]
        else:
            # Has bypass flag - show all results
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
        if trigger_lower.endswith(" ") and query_lower.startswith(trigger_lower):
            return query[len(trigger) :].strip()

        # Handle trigger without space (e.g., "app")
        trigger_word = trigger.strip().lower()
        if query_lower.startswith(trigger_word):
            # Check if it's followed by space or end of string
            if len(query) == len(trigger_word):
                return ""
            elif len(query) > len(trigger_word) and query[len(trigger_word)] == " ":
                return query[len(trigger_word) + 1 :].strip()
            elif len(query) > len(trigger_word):
                # No space after trigger word, extract rest
                return query[len(trigger_word) :].strip()

        return ""

    def _show_available_triggers(self):
        """Show available triggers when launcher is first opened."""
        trigger_suggestions = self._get_trigger_suggestions("")
        self.results = trigger_suggestions  # Show all available triggers without limit
        self.selected_index = 0
        self._update_results_display()

    def _detect_trigger(self, query: str) -> Tuple[Optional[object], str]:
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

    def _get_trigger_suggestions(self, query: str) -> List[Result]:
        """
        Get trigger suggestions based on the current query.

        Args:
            query: The search query

        Returns:
            List of Result objects showing available triggers
        """
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
                        "plugin": plugin,
                        "trigger": trigger,
                        "examples": [],
                    }

        # Get max examples to show from configuration
        max_examples = self.trigger_config.settings.get("max_examples_shown", 2)

        # Show trigger suggestions based on query
        if query_lower:
            # Show triggers that match the query
            for trigger_clean, _ in all_triggers.items():
                if trigger_clean.lower().startswith(query_lower):
                    result = self._create_trigger_result(trigger_clean, max_examples)
                    suggestions.append(result)
        else:
            # Empty query - show all available triggers
            for trigger_clean, _ in all_triggers.items():
                result = self._create_trigger_result(trigger_clean, max_examples)
                suggestions.append(result)

        return suggestions  # Return all trigger suggestions without limit

    def _create_trigger_result(self, trigger_clean: str, max_examples: int) -> Result:
        """Create a Result object for a trigger suggestion."""
        examples = self.trigger_config.get_trigger_examples(trigger_clean)
        icon_name = self.trigger_config.get_trigger_icon(trigger_clean)
        description = self.trigger_config.get_trigger_description(trigger_clean)

        return Result(
            title=f"{trigger_clean}",
            subtitle=f"{description} - {', '.join(examples[:max_examples])}",
            icon_markup=icon_name,
            action=lambda t=trigger_clean: self._activate_trigger(t),
            # Shorter triggers get higher relevance
            relevance=100 - len(trigger_clean),
            data={"type": "trigger_suggestion", "trigger": trigger_clean},
        )

    def _activate_trigger(self, trigger: str):
        """
        Activate a trigger by setting it in the search entry.

        Args:
            trigger: The trigger keyword to activate
        """
        # Set the trigger text in the search entry
        trigger_text = f"{trigger} "
        self.search_entry.set_text(trigger_text)
        self.search_entry.grab_focus()

        def clear_selection():
            if hasattr(self.search_entry, "set_position"):
                self.search_entry.set_position(-1)  # Move caret to end
            if hasattr(self.search_entry, "select_region"):
                self.search_entry.select_region(
                    len(trigger_text), len(trigger_text)
                )  # No selection
            return False  # Only run once

        GLib.idle_add(clear_selection)

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

    def _execute_external_command(self, command_string: str):
        """Execute a command externally without showing the launcher UI.

        Args:
            command_string: Full command string (e.g., "wall random", "calc 2+2")

        Returns:
            Result of the command execution or None if failed
        """
        try:
            # Parse the command to extract trigger and query
            parts = command_string.strip().split(" ", 1)
            if not parts:
                return None

            trigger_part = parts[0]
            query_part = parts[1] if len(parts) > 1 else ""

            # Find the plugin that handles this trigger
            triggered_plugin = None

            for plugin in self.plugin_manager.get_active_plugins():
                trigger = plugin.get_active_trigger(f"{trigger_part} ")
                if trigger:
                    triggered_plugin = plugin
                    break

            if not triggered_plugin:
                print(f"No plugin found for trigger: {trigger_part}")
                return None

            # Query the plugin with the remaining query
            try:
                results = triggered_plugin.query(query_part)
                if not results:
                    print(f"No results found for query: {query_part}")
                    return None

                # Find the first result that matches the query exactly or has highest relevance
                best_result = None
                for result in results:
                    # For exact matches like "random", execute immediately
                    if (
                        hasattr(result, "data")
                        and result.data
                        and result.data.get("action") == query_part.strip()
                    ):
                        best_result = result
                        break
                    # For partial matches, take the first high-relevance result
                    elif not best_result and result.relevance >= 0.9:
                        best_result = result

                # If no exact match, take the first result
                if not best_result and results:
                    best_result = results[0]

                if best_result:
                    # Execute the result action
                    try:
                        result_value = best_result.activate()
                        print(f"External command executed: {command_string}")
                        return result_value
                    except Exception as e:
                        print(f"Error executing result action: {e}")
                        return None
                else:
                    print(f"No suitable result found for: {command_string}")
                    return None

            except Exception as e:
                print(f"Error querying plugin {triggered_plugin.name}: {e}")
                return None

        except Exception as e:
            print(f"Error executing external command '{command_string}': {e}")
            return None

    def _update_results_display(self):
        """Update the results display."""
        # Skip if still initializing or results_box not ready
        if getattr(self, "_initializing", True) or not hasattr(self, "results_box"):
            return

        # Update input field with trigger indication (Albert-style)
        self._update_input_action_text()

        # Clear existing results
        for child in self.results_box.get_children():
            self.results_box.remove(child)

        # Add new results
        for i, result in enumerate(self.results):
            # Check if this result has a custom widget
            if result.custom_widget:
                # Ensure the widget is not already parented
                parent = result.custom_widget.get_parent()
                if parent:
                    parent.remove(result.custom_widget)

                result.custom_widget.show_all()  # Ensure widget is visible
                self.results_box.add(result.custom_widget)
            else:
                # Create normal result item
                result_item = ResultItem(
                    result=result, selected=(i == self.selected_index)
                )
                result_item.clicked.connect(
                    lambda _, idx=i: self._on_result_clicked(result_item, idx)
                )
                self.results_box.add(result_item)

        self.results_box.show_all()

        # Show/hide scroll container based on results
        if self.results:
            self.results_scroll.show()
        else:
            self.results_scroll.hide()

    def _update_input_action_text(self):
        """Update the input field with action text (Albert-style)."""
        # Check if search_entry is initialized
        if not hasattr(self, "search_entry") or self.search_entry is None:
            return

        # Get the current input text
        current_text = self.search_entry.get_text()

        if self.triggered_plugin:
            if self.results:
                # Show the first result as action text
                first_result = self.results[0]
                action_text = first_result.title

                # For calculator results, show the evaluation
                if hasattr(first_result, "data") and "result" in first_result.data:
                    action_text = str(first_result.data["result"])

                # Set placeholder to show the action text
                if action_text and action_text != current_text:
                    self.search_entry.set_placeholder_text(
                        f"{current_text} → {action_text}"
                    )
                else:
                    self.search_entry.set_placeholder_text(
                        f"[{self.active_trigger.strip()}] searching..."
                    )
            else:
                # In trigger mode but no results yet
                if current_text == self.active_trigger.strip():
                    # Just the trigger keyword
                    self.search_entry.set_placeholder_text(
                        f"[{self.active_trigger.strip()}] ready - type to search"
                    )
                else:
                    # Searching within trigger
                    self.search_entry.set_placeholder_text(
                        f"[{self.active_trigger.strip()}] searching..."
                    )
        else:
            # Not in trigger mode - show trigger help
            if current_text == ":":
                self.search_entry.set_placeholder_text(
                    "Showing all available triggers."
                )
            elif current_text:
                self.search_entry.set_placeholder_text(
                    "Type trigger keyword (calc, app, file, system...)"
                )
            else:
                self.search_entry.set_placeholder_text(
                    "Type trigger keyword: calc, app, file, system..."
                )

    def _clear_results(self):
        """Clear all results."""
        self.results = []
        self.selected_index = 0
        for child in self.results_box.get_children():
            self.results_box.remove(child)
        self.results_scroll.hide()

    def _handle_escape_key(self) -> bool:
        """Handle escape key press."""
        # First check if there's a password entry widget that should handle Escape
        password_entry_widget = self._find_password_entry_widget()
        if password_entry_widget:
            # Cancel the password entry
            password_entry_widget.cancel_password_entry()
            return True
        elif self.opened_with_trigger:
            # If launcher was opened with a trigger keyword, close directly
            self.close_launcher()
            return True
        elif self.triggered_plugin:
            # Exit trigger mode
            self.triggered_plugin = None
            self.active_trigger = ""
            self.search_entry.set_text("")
            self._clear_results()
            return True
        else:
            # Hide launcher
            self.close_launcher()
            return True

    def _handle_backspace_key(self) -> bool:
        """Handle backspace key press in trigger mode."""
        if self.triggered_plugin:
            trigger_text = self.active_trigger.strip()
            current_text = self.search_entry.get_text()

            # Set flag to prevent search change handler from interfering
            self._processing_backspace = True

            # Allow normal backspace behavior first, then check if we need to exit trigger mode
            # Don't intercept the backspace - let GTK handle it normally

            # Schedule a check after the backspace is processed
            def check_trigger_after_backspace():
                try:
                    # Get the text after backspace has been processed
                    new_text = self.search_entry.get_text()

                    # Check if we should exit trigger mode
                    # We need to check if the text still matches the trigger pattern
                    should_exit_trigger = False

                    # If the active trigger ends with a space (like "calc "),
                    # we should exit if the text doesn't contain that space anymore
                    if self.active_trigger.endswith(" "):
                        # For triggers like "calc ", exit if text is just "calc" or doesn't start with "calc "
                        trigger_with_space = self.active_trigger.lower()
                        if not new_text.lower().startswith(trigger_with_space):
                            should_exit_trigger = True
                    else:
                        # For triggers without space, exit if text doesn't start with trigger
                        if not new_text.lower().startswith(trigger_text.lower()):
                            should_exit_trigger = True

                    if should_exit_trigger:
                        self.triggered_plugin = None
                        self.active_trigger = ""
                        self._clear_results()
                        # Don't clear the text - let the user's edit stand

                    # If we're still in trigger mode but the text changed, update the search
                    elif self.triggered_plugin and new_text != current_text:
                        # Trigger a search with the new text
                        self.query = new_text
                        GLib.timeout_add(50, self._perform_search, new_text)

                finally:
                    # Clear the backspace processing flag
                    self._processing_backspace = False

                return False  # Don't repeat

            # Use idle_add to check after the backspace is processed
            GLib.idle_add(check_trigger_after_backspace)

            # Allow the normal backspace to proceed
            return False

        # Let normal backspace behavior continue for other cases
        return False

    def _on_key_press(self, _widget, event):
        """Handle key press events."""
        keyval = event.keyval

        # Escape - handle password entry, exit trigger mode, or hide launcher
        if keyval == Gdk.KEY_Escape:
            return self._handle_escape_key()

        # Backspace - handle trigger mode backspace behavior
        if keyval == Gdk.KEY_BackSpace:
            return self._handle_backspace_key()

        # Up/Down - navigate results (alternative to Tab)
        if keyval == Gdk.KEY_Up:
            if self.focus_mode == "results" and self.results:
                if self.selected_index > 0:
                    # Move to previous result
                    self.selected_index -= 1
                    self._update_selection()
                else:
                    # At first result, go back to search entry
                    self.focus_mode = "search"
                    self._focus_search_entry_without_selection()
            elif self.results:
                # If not in results mode but have results, enter results mode at last item
                self.focus_mode = "results"
                self.selected_index = len(self.results) - 1
                self._update_selection()
            return True

        if keyval == Gdk.KEY_Down:
            if self.focus_mode == "results" and self.results:
                if self.selected_index < len(self.results) - 1:
                    # Move to next result
                    self.selected_index += 1
                    self._update_selection()
                else:
                    # At last result, wrap around to first result
                    self.selected_index = 0
                    self._update_selection()
            elif self.results:
                # If not in results mode but have results, enter results mode at first item
                self.focus_mode = "results"
                self.selected_index = 0
                self._update_selection()
            return True

        # Enter - activate selected result or header button
        if keyval == Gdk.KEY_Return:
            # Check if we're in header mode
            if self.focus_mode == "header":
                # Activate the selected header button
                self.header_buttons[self.header_button_index].emit("clicked")
                return True

            # Check for Shift+Enter for alternative actions
            if event.state & Gdk.ModifierType.SHIFT_MASK:
                if self.results and 0 <= self.selected_index < len(self.results):
                    result = self.results[self.selected_index]
                    if result.data:
                        # Check for generic alternative action first
                        if result.data.get("alt_action"):
                            result.data["alt_action"]()
                            return True
                        # Fallback to pin_action for backward compatibility
                        elif result.data.get("pin_action"):
                            result.data["pin_action"]()
                            return True

            # Check if the selected result has a custom widget with Entry fields
            if self.results and 0 <= self.selected_index < len(self.results):
                result = self.results[self.selected_index]
                if result.custom_widget:
                    # Check if the custom widget contains Entry widgets that should handle Enter
                    if self._custom_widget_has_entry(result.custom_widget):
                        # Let the custom widget handle the Enter key
                        # Find the focused Entry widget and trigger its activate signal
                        focused_entry = self._find_focused_entry_in_widget(
                            result.custom_widget
                        )
                        if focused_entry:
                            focused_entry.emit("activate")
                            return True

            # Normal Enter behavior
            self._activate_selected()
            return True

        # Tab - cycle through focus areas, results, and header buttons
        if keyval == Gdk.KEY_Tab:
            if event.state & Gdk.ModifierType.SHIFT_MASK:
                # Shift+Tab - reverse direction
                if self.focus_mode == "header":
                    # Navigate between header buttons in reverse
                    self._navigate_header_buttons_backward()
                elif self.focus_mode == "results":
                    # Navigate through results in reverse
                    self._navigate_results_backward()
                else:
                    self._cycle_focus_backward()
            else:
                # Tab - forward direction
                if self.focus_mode == "header":
                    # Navigate between header buttons forward
                    self._navigate_header_buttons_forward()
                elif self.focus_mode == "results":
                    # Navigate through results forward
                    self._navigate_results_forward()
                else:
                    self._cycle_focus_forward()
            return True

        # Page Up/Page Down - navigate results faster
        if keyval == Gdk.KEY_Page_Up:
            if self.results:
                self.selected_index = max(0, self.selected_index - PAGE_NAVIGATION_STEP)
                self._update_selection()
            return True

        if keyval == Gdk.KEY_Page_Down:
            if self.results:
                self.selected_index = min(
                    len(self.results) - 1, self.selected_index + PAGE_NAVIGATION_STEP
                )
                self._update_selection()
            return True

        # Home/End - go to first/last result
        if keyval == Gdk.KEY_Home:
            if self.results:
                self.selected_index = 0
                self._update_selection()
            return True

        if keyval == Gdk.KEY_End:
            if self.results:
                self.selected_index = len(self.results) - 1
                self._update_selection()
            return True

        # Forward other keys to custom widgets if they can handle them
        if self.results and 0 <= self.selected_index < len(self.results):
            result = self.results[self.selected_index]
            if result.custom_widget and hasattr(result.custom_widget, "on_key_press"):
                # Try to forward the key event to the custom widget
                if result.custom_widget.on_key_press(result.custom_widget, event):
                    return True

        return False

    def _custom_widget_has_entry(self, widget):
        """Check if a custom widget contains Entry widgets."""

        if isinstance(widget, Entry):
            return True

        # Check children recursively
        if hasattr(widget, "get_children"):
            for child in widget.get_children():
                if self._custom_widget_has_entry(child):
                    return True

        return False

    def _find_focused_entry_in_widget(self, widget):
        """Find the focused Entry widget within a custom widget."""

        if isinstance(widget, Entry):
            # Try multiple ways to check if this Entry is focused
            try:
                if widget.has_focus() or widget.is_focus():
                    return widget
                # Also check if this is the only Entry in the widget (likely to be the target)
                return widget
            except:
                # If focus checking fails, assume this Entry should handle the event
                return widget

        # Check children recursively
        if hasattr(widget, "get_children"):
            for child in widget.get_children():
                focused_entry = self._find_focused_entry_in_widget(child)
                if focused_entry:
                    return focused_entry

        return None

    def _find_password_entry_widget(self):
        """Find a NetworkPasswordEntry widget in the current results."""
        for result in self.results:
            if result.custom_widget:
                # Check if this is a NetworkPasswordEntry widget
                if (
                    hasattr(result.custom_widget, "__class__")
                    and result.custom_widget.__class__.__name__
                    == "NetworkPasswordEntry"
                ):
                    return result.custom_widget
                # Also check if it has the cancel_password_entry method (duck typing)
                elif hasattr(result.custom_widget, "cancel_password_entry"):
                    return result.custom_widget
        return None

    def _on_entry_activate(self, _entry):
        """Handle entry activation (Enter key)."""
        self._activate_selected()

    def _on_result_clicked(self, _result_item, index):
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
                is_selected = i == self.selected_index
                child.set_selected(is_selected)
                if is_selected:
                    selected_widget = child
            # For custom widgets, we don't need to handle selection visually
            # since they manage their own interaction

        # Focus custom widgets when selected for keyboard interaction
        if self.results and 0 <= self.selected_index < len(self.results):
            result = self.results[self.selected_index]
            if result.custom_widget and result.custom_widget.get_can_focus():
                # Give focus to the custom widget for keyboard interaction
                result.custom_widget.grab_focus()

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
                item_height = DEFAULT_ITEM_HEIGHT
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
            # Scroll if needed
            if item_top < visible_top + SCROLL_PADDING:
                # Item is above visible area - scroll up
                new_scroll = max(0, item_top - SCROLL_PADDING)
                vadjustment.set_value(new_scroll)
            elif item_bottom > visible_bottom - SCROLL_PADDING:
                # Item is below visible area - scroll down
                new_scroll = min(max_scroll, item_bottom - page_size + SCROLL_PADDING)
                vadjustment.set_value(new_scroll)

    def _ensure_selected_visible(self):
        """Alternative method to ensure selected item is visible using GTK methods."""
        if (
            not self.results
            or self.selected_index < 0
            or self.selected_index >= len(self.results)
        ):
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
                        target_pos = (
                            allocation.y - (page_size / 2) + (allocation.height / 2)
                        )
                        target_pos = max(
                            0, min(target_pos, vadjustment.get_upper() - page_size)
                        )
                        vadjustment.set_value(target_pos)
            except Exception as e:
                print(f"Error in _ensure_selected_visible: {e}")

        return False  # Don't repeat the idle callback

    def _cycle_focus_forward(self):
        """Cycle focus forward: search -> results -> header (first button)"""
        if self.focus_mode == "search":
            if self.results:
                self.focus_mode = "results"
                self._update_selection()
            else:
                self.focus_mode = "header"
                self.header_button_index = 0
                self._update_header_focus()
        elif self.focus_mode == "results":
            self.focus_mode = "header"
            self.header_button_index = 0
            self._update_header_focus()

    def _cycle_focus_backward(self):
        """Cycle focus backward: search -> header (last button) -> results -> search"""
        if self.focus_mode == "search":
            self.focus_mode = "header"
            self.header_button_index = len(self.header_buttons) - 1
            self._update_header_focus()
        elif self.focus_mode == "results":
            self.focus_mode = "search"
            self._clear_header_focus()
            self._focus_search_entry_without_selection()

    def _update_header_focus(self):
        """Update focus to the selected header button."""
        # Remove focus from all buttons first
        self._clear_header_focus()

        # Add focus style to selected button
        selected_button = self.header_buttons[self.header_button_index]
        selected_button.add_style_class("focused")
        selected_button.grab_focus()

    def _clear_header_focus(self):
        """Remove focus styling from all header buttons."""
        for button in self.header_buttons:
            button.remove_style_class("focused")

    def _focus_search_entry_without_selection(self):
        """Focus search entry and position cursor at end without selecting text."""
        # First grab focus
        self.search_entry.grab_focus()

        # Use multiple approaches to prevent text selection
        def clear_selection():
            try:
                text_length = len(self.search_entry.get_text())

                # Method 1: Set position and clear selection
                if hasattr(self.search_entry, "set_position"):
                    self.search_entry.set_position(text_length)
                if hasattr(self.search_entry, "select_region"):
                    self.search_entry.select_region(text_length, text_length)

                # Method 2: Try to access underlying GTK widget
                try:
                    # For fabric Entry widgets, try to get the actual GTK Entry
                    if hasattr(self.search_entry, "_entry"):
                        gtk_entry = self.search_entry._entry
                    elif (
                        hasattr(self.search_entry, "get_children")
                        and self.search_entry.get_children()
                    ):
                        gtk_entry = self.search_entry.get_children()[0]
                    else:
                        gtk_entry = self.search_entry

                    if hasattr(gtk_entry, "set_position"):
                        gtk_entry.set_position(text_length)
                    if hasattr(gtk_entry, "select_region"):
                        gtk_entry.select_region(text_length, text_length)

                except Exception:
                    pass

            except Exception as e:
                print(f"Could not clear selection: {e}")
            return False

        # Schedule clearing selection after focus is established
        GLib.idle_add(clear_selection)
        # Also try with a small delay as backup
        GLib.timeout_add(CURSOR_POSITION_DELAY_MS, clear_selection)

    def _navigate_header_buttons_forward(self):
        """Navigate to next header button or exit header mode."""
        if self.header_button_index < len(self.header_buttons) - 1:
            # Move to next button
            self.header_button_index += 1
            self._update_header_focus()
        else:
            # Exit header mode and go to search
            self.focus_mode = "search"
            self._clear_header_focus()
            self._focus_search_entry_without_selection()

    def _navigate_header_buttons_backward(self):
        """Navigate to previous header button or exit header mode."""
        if self.header_button_index > 0:
            # Move to previous button
            self.header_button_index -= 1
            self._update_header_focus()
        else:
            # Exit header mode and go to results or search
            if self.results:
                self.focus_mode = "results"
                self.selected_index = len(self.results) - 1  # Go to last result
                self._clear_header_focus()
                self._update_selection()
            else:
                self.focus_mode = "search"
                self._clear_header_focus()
                self._focus_search_entry_without_selection()

    def _navigate_results_forward(self):
        """Navigate to next result or wrap around to first result."""
        if self.results and self.selected_index < len(self.results) - 1:
            # Move to next result
            self.selected_index += 1
            self._update_selection()
        else:
            # At last result, wrap around to first result
            self.selected_index = 0
            self._update_selection()

    def _navigate_results_backward(self):
        """Navigate to previous result or exit results mode."""
        if self.results and self.selected_index > 0:
            # Move to previous result
            self.selected_index -= 1
            self._update_selection()
        else:
            # Exit results mode and go to search
            self.focus_mode = "search"
            self._focus_search_entry_without_selection()

    def _activate_selected(self):
        """Activate the currently selected result."""
        if self.results and 0 <= self.selected_index < len(self.results):
            result = self.results[self.selected_index]
            try:
                # Check if this result has a custom widget
                if result.custom_widget:
                    # For custom widgets, we don't activate them since they're already displayed
                    # The widget handles its own interactions
                    return

                # Check if this is a trigger suggestion or should keep launcher open
                is_trigger_suggestion = (
                    result.data and result.data.get("type") == "trigger_suggestion"
                )
                keep_launcher_open = result.data and result.data.get(
                    "keep_launcher_open", False
                )

                # Activate the result
                result.activate()

                # Only hide launcher if it's not a trigger suggestion and doesn't have keep_launcher_open flag
                if not is_trigger_suggestion and not keep_launcher_open:
                    self.close_launcher()
                # For trigger suggestions and keep_launcher_open actions, the launcher stays open

            except Exception as e:
                print(f"Error activating result: {e}")
