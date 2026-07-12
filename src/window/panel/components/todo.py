from datetime import datetime

from fabric.utils import GLib
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from fabric.widgets.label import Label

from services.todo import get_todo_service
from shared.window.animated_scrollwindow import AnimatedScrollable
from shared.window.applet_window import AppletWindow
from utils.utils import svg_file


class TodoItem(Box):
    """Individual todo item widget"""

    def __init__(self, todo_data, todo_list_widget, **kwargs):
        self.todo_data = todo_data
        self.todo_list_widget = todo_list_widget
        self.editing = False

        super().__init__(
            name="todo-item",
            orientation="h",
            spacing=8,
            **kwargs,
        )

        self._build_ui()

    def _build_ui(self):
        """Build the todo item UI"""
        # Checkbox for completion - using SVG icons
        checkbox_icon = (
            "checkbox-check.svg"
            if self.todo_data["completed"]
            else "checkbox-uncheck.svg"
        )
        self.checkbox_icon = svg_file(
            "todo/" + checkbox_icon,
            name="todo-checkbox-icon",
            size=24,
        )
        self.checkbox = Button(
            name="todo-checkbox",
            child=self.checkbox_icon,
            on_clicked=self._toggle_completion,
        )

        # Todo text (can be converted to entry for editing)
        text_content = self.todo_data["text"]
        if self.todo_data["completed"]:
            text_content = f"<s>{text_content}</s>"

        self.text_label = Label(
            markup=text_content,
            name="todo-text",
            h_align="start",
            h_expand=True,
            line_wrap="word-char",
            style_classes=(
                ["title-widget"]
                if not self.todo_data["completed"]
                else ["status-label"]
            ),
        )

        # Date/time label
        created_at = datetime.fromisoformat(self.todo_data["created_at"])
        date_text = created_at.strftime("%b %d, %Y at %I:%M %p")

        self.date_label = Label(
            label=date_text,
            name="todo-date",
            h_align="start",
            style_classes=["todo-date-text"],
        )

        self.text_entry = Entry(
            name="todo-text-entry",
            text=self.todo_data["text"],
            h_expand=True,
            visible=False,
        )
        self.text_entry.connect("activate", self._save_edit)

        # Priority indicator
        # priority_symbols = {"high": "🔴", "medium": "🟡", "low": "🟢"}
        #
        # self.priority_label = Label(
        #     label=priority_symbols.get(self.todo_data["priority"], "🟡"),
        #     name="todo-priority-label",
        # )
        # self.priority_button = Button(
        #     name="todo-priority",
        #     size=(20, 20),
        #     child=self.priority_label,
        #     on_clicked=self._cycle_priority,
        # )
        #
        # Edit button - using SVG icon
        self.edit_icon = svg_file(
            "todo/edit.svg",
            name="todo-edit-icon",
            size=12,
        )
        self.edit_button = Button(
            name="todo-edit",
            child=self.edit_icon,
            on_clicked=self._start_edit,
        )

        # Delete button - using SVG icon
        self.delete_icon = svg_file(
            "todo/delete-symbolic.svg",
            name="todo-delete-icon",
            size=12,
        )
        self.delete_button = Button(
            name="todo-delete",
            child=self.delete_icon,
            on_clicked=self._delete_todo,
        )

        # Text container that switches between label and entry
        self.text_container = Box(
            orientation="v",
            h_expand=True,
            children=[
                Box(orientation="h", children=[self.text_label]),
                self.date_label,
            ],
        )

        for child in [
            self.checkbox,
            self.text_container,
            self.edit_button,
            self.delete_button,
        ]:
            self.add(child)

    def _toggle_completion(self, *_):
        """Toggle todo completion status"""
        get_todo_service().toggle_todo(self.todo_data["id"])

    def _cycle_priority(self, *_):
        """Cycle through priority levels"""
        priorities = ["low", "medium", "high"]
        current_priority = self.todo_data.get("priority", "medium")
        current_index = priorities.index(current_priority)
        new_priority = priorities[(current_index + 1) % len(priorities)]
        get_todo_service().set_priority(self.todo_data["id"], new_priority)

    def _start_edit(self, *_):
        """Start editing the todo text"""
        if self.editing:
            return

        self.editing = True
        self.text_container.children = [
            Box(orientation="h", children=[self.text_entry]),
            self.date_label,
        ]
        self.text_entry.set_visible(True)
        self.text_entry.grab_focus()
        self.text_entry.set_position(-1)  # Move cursor to end

    def _save_edit(self, *_):
        """Save the edited todo text"""
        if not self.editing:
            return

        new_text = self.text_entry.get_text().strip()
        if new_text:
            get_todo_service().edit_todo(self.todo_data["id"], new_text)

        self._cancel_edit()

    def _cancel_edit(self):
        """Cancel editing and revert to label"""
        self.editing = False
        self.text_container.children = [
            Box(orientation="h", children=[self.text_label]),
            self.date_label,
        ]
        self.text_entry.set_visible(False)

    def _delete_todo(self, *_):
        """Delete this todo"""
        get_todo_service().delete_todo(self.todo_data["id"])

    def update_from_data(self, todo_data):
        """Update the widget from new todo data"""
        self.todo_data = todo_data

        # Update checkbox icon by recreating it
        checkbox_icon = (
            "checkbox-check.svg" if todo_data["completed"] else "checkbox-uncheck.svg"
        )
        new_checkbox_icon = svg_file(
            "todo/" + checkbox_icon,
            name="todo-checkbox-icon",
            size=20,
        )
        old_child = self.checkbox.get_child()
        if old_child:
            self.checkbox.remove(old_child)
        self.checkbox.add(new_checkbox_icon)
        self.checkbox_icon = new_checkbox_icon

        # Update text and styling with markup
        text_content = todo_data["text"]
        if todo_data["completed"]:
            text_content = f"<s>{text_content}</s>"

        self.text_label.set_markup(text_content)
        self.text_label.style_classes = (
            ["title-widget"] if not todo_data["completed"] else ["status-label"]
        )

        # Update date/time
        created_at = datetime.fromisoformat(todo_data["created_at"])
        date_text = created_at.strftime("%b %d, %Y at %I:%M %p")
        self.date_label.set_label(date_text)


class TodoListWidget(AppletWindow):
    """Main todo list window"""

    def __init__(self, parent=None, pointing_to=None, **kwargs):
        super().__init__(
            parent=parent,
            pointing_to=pointing_to,
            layer="top",
            title="modus-todo",
            anchor="top right",
            margin="2px 10px 0px 0px",
            exclusivity="auto",
            name="todo-list-menu",
            visible=False,
            **kwargs,
        )

        self.todo_items = {}  # Maps todo IDs to TodoItem widgets

        # Register callback with todo service
        get_todo_service().add_callback(self._on_todo_event)

        self._build_ui()
        self._refresh_todos()

        # Add keybinding for escape
        self.add_keybinding("Escape", self.hide_todo_list)

    def _build_ui(self):
        """Build the main UI"""
        # Header with title and stats
        self.stats_label = Label(
            label="",
            name="todo-stats",
            style_classes=["status-label"],
            h_align="start",
        )

        self.header = Box(
            name="todo-header",
            orientation="v",
            children=[
                Label(
                    label="Todo List",
                    name="todo-title",
                    style_classes=["title"],
                    h_align="start",
                ),
                self.stats_label,
            ],
        )

        # Add new todo section
        self.new_todo_entry = Entry(
            name="new-todo-entry",
            placeholder_text="Add a new task...",
            h_expand=True,
        )
        self.new_todo_entry.connect("activate", self._add_todo)

        # Add button - using SVG icon
        self.add_icon = svg_file(
            "todo/plus-symbolic.svg",
            name="add-todo-icon",
            size=12,
        )
        self.add_button = Button(
            name="add-todo-button",
            child=self.add_icon,
            on_clicked=self._add_todo,
        )

        self.add_section = Box(
            name="todo-add-section",
            orientation="h",
            spacing=8,
            children=[
                self.new_todo_entry,
                self.add_button,
            ],
        )

        # Todo items container
        self.todos_container = Box(
            name="todos-container",
            orientation="v",
            spacing=4,
            v_expand=True,
        )

        # Scrolled window for todos
        self.scrolled = AnimatedScrollable(
            name="todos-scrolled",
            min_content_size=(400, 300),
            max_content_size=(-1, 500),
            child=self.todos_container,
            h_scrollbar_policy="automatic",
            v_scrollbar_policy="automatic",
            propagate_height=False,
            v_expand=True,
        )

        # Clear completed button
        self.clear_button = Button(
            name="clear-completed-button",
            label="Clear Completed",
            style_classes=["status-label"],
            on_clicked=self._clear_completed,
        )

        # Main container
        self.main_container = Box(
            name="todo-main-container",
            orientation="v",
            spacing=8,
            children=[
                self.header,
                self.add_section,
                self.scrolled,
                self.clear_button,
            ],
        )

        self.add(self.main_container)

    def _add_todo(self, *_):
        """Add a new todo"""
        text = self.new_todo_entry.get_text().strip()
        if text:
            get_todo_service().add_todo(text)
            self.new_todo_entry.set_text("")

    def _clear_completed(self, *_):
        """Clear all completed todos"""
        get_todo_service().clear_completed()

    def _on_todo_event(self, event_type, data=None):
        """Handle todo service events via callback"""
        if (
            event_type == "todos-changed"
            or event_type == "todo-added"
            or event_type == "todo-deleted"
        ):
            GLib.idle_add(self._refresh_todos)
        elif event_type in ["todo-toggled", "todo-edited", "todo-priority-changed"]:
            if data and data["id"] in self.todo_items:
                GLib.idle_add(
                    lambda: self.todo_items[data["id"]].update_from_data(data)
                )
            GLib.idle_add(self._update_stats)

    def _refresh_todos(self, *_):
        """Refresh the entire todo list"""
        # Clear existing items
        self.todo_items.clear()
        for child in self.todos_container.get_children():
            self.todos_container.remove(child)

        # Get all todos
        todos = get_todo_service().todos

        # Sort todos: incomplete first, then by priority, then by creation date
        def sort_key(todo):
            priority_order = {"high": 0, "medium": 1, "low": 2}
            return (
                todo["completed"],  # False (incomplete) comes before True (completed)
                priority_order.get(todo.get("priority", "medium"), 1),
                todo["created_at"],
            )

        sorted_todos = sorted(todos, key=sort_key)

        # Create todo item widgets and add them to the container
        for todo in sorted_todos:
            todo_item = TodoItem(todo, self)
            self.todo_items[todo["id"]] = todo_item
            self.todos_container.add(todo_item)

        # Ensure they are visible
        self.todos_container.show_all()

        # Update stats
        self._update_stats()

    def _update_stats(self):
        """Update the statistics display"""
        stats = get_todo_service().get_stats()
        stats_text = f"{stats['pending']} pending, {stats['completed']} completed"
        self.stats_label.set_label(stats_text)

    def set_visible(self, visible):
        """Override set_visible for debugging"""
        super().set_visible(visible)

    def hide_todo_list(self, *_):
        """Hide the todo list"""
        self.hide()
        self.hide()

    def destroy(self):
        """Clean up when destroyed"""
        # Remove callback from todo service
        get_todo_service().remove_callback(self._on_todo_event)

        super().destroy()
