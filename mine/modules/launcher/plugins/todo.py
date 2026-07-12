from collections.abc import Iterator

from fabric.utils import Gdk, idle_add, remove_handler
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label

from modules.launcher.base import LauncherPlugin
from services import TodoService


class TodoPlugin(LauncherPlugin):
    @property
    def name(self) -> str:
        return "todo"

    @property
    def icon(self) -> str:
        return "view-list-symbolic"

    @property
    def keywords(self) -> list[str]:
        return ["todo"]

    def __init__(self, handler):
        super().__init__(handler)
        self.todo_service = TodoService()
        self._query_handler: int = 0
        self.current_slots: list = []
        self.todos: list = []

    def on_search(self, text: str) -> None:
        self.query_todos(text)

    def stop(self):
        if self._query_handler:
            remove_handler(self._query_handler)
            self._query_handler = 0
        self.current_slots.clear()

    def query_todos(self, text: str) -> None:
        self.handler.start("todos")
        self.current_slots.clear()
        text_stripped = text.strip()

        commands = {
            "add": self._handle_add_command,
            "done": self._handle_done_command,
            "remove": self._handle_remove_command,
            "edit": self._handle_edit_command,
            "clear": self._handle_clear_command,
            "help": lambda t: self._show_command_help(),
        }

        for prefix, handler in commands.items():
            if text_stripped.startswith(prefix):
                handler(text)
                return

        self._load_and_display_todos(text)

    def _load_and_display_todos(self, text: str) -> None:
        result = self.todo_service.list_todos()
        if not result["success"]:
            self._show_error_message(f"Failed to load todos: {result['error']}")
            return

        self.todos = result["data"]

        if not self.todos:
            self._show_no_todos()
            return

        filtered_todos = self._filter_todos(text)
        # Convert to list to check if empty, as we need to know if we should show "no results"
        filtered_list = list(filtered_todos)
        if not filtered_list:
            self._show_no_results()
            return

        self._query_handler = idle_add(
            self._bake_next_todo_slot, iter(filtered_list), pin=True
        )

    def _filter_todos(self, text: str) -> Iterator[dict]:
        if not text.strip():
            return iter(self.todos)

        text_lower = text.lower()
        return iter(
            todo
            for todo in self.todos
            if (
                text_lower in todo.get("title", "").lower()
                or text_lower in todo.get("description", "").lower()
                or any(text_lower in tag.lower() for tag in todo.get("tags", []))
            )
        )

    def _show_no_todos(self) -> None:
        self.handler.slot_ready(
            Button(
                style_classes="app-slot todo-no-todos",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Label(
                            label="No todos found",
                            style_classes="todo-no-todos-text",
                            h_align="center",
                        ),
                    ],
                ),
                tooltip_text="Use 'add title description' to add todos",
            ),
            "todos",
        )
        self.handler.done()

    def _show_no_results(self) -> None:
        self.handler.slot_ready(
            Button(
                style_classes="app-slot todo-no-results",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Label(
                            label="No todos match your search",
                            style_classes="todo-no-results-text",
                            h_align="center",
                        ),
                    ],
                ),
            ),
            "todos",
        )
        self.handler.done()

    def _bake_next_todo_slot(self, iterator: Iterator[dict]) -> bool:
        try:
            todo = next(iterator)
        except StopIteration:
            idle_add(self.handler.done)
            return False

        self._create_todo_slot(todo)
        return True

    def _create_todo_slot(self, todo: dict) -> None:
        todo_id = todo.get("id")
        title = todo.get("title", "")
        description = todo.get("description", "")
        status = todo.get("status", "pending")
        priority = todo.get("priority", "medium")
        tags = todo.get("tags", [])

        status_icon = "✓" if status == "completed" else "○"
        status_color = "completed" if status == "completed" else "pending"

        priority_icons = {"low": "↓", "medium": "→", "high": "↑"}
        priority_icon = priority_icons.get(priority, "→")

        title_label = Label(
            label=f"{status_icon} {title}",
            style_classes=f"todo-title todo-{status_color}",
            h_align="start",
            max_chars_width=30,
            ellipsization="end",
        )

        description_label = Label(
            label=description if description else "No description",
            style_classes="todo-description",
            h_align="start",
            max_chars_width=40,
            ellipsization="end",
        )

        tags_label = Label(
            label=f"{priority_icon} {' '.join(f'#{tag}' for tag in tags[:3])}"
            if tags
            else f"{priority_icon} {priority}",
            style_classes="todo-tags",
            h_align="start",
            max_chars_width=35,
            ellipsization="end",
        )

        slot_widget = Button(
            style_classes=f"app-slot todo-slot todo-{status_color}",
            child=Box(
                orientation="v",
                spacing=4,
                children=[
                    title_label,
                    description_label,
                    tags_label,
                ],
            ),
            tooltip_text=f"Click to toggle completion\nShift+Enter to toggle completion\nAlt+Enter to remove todo\nPriority: {priority}\nTags: {', '.join(tags) if tags else 'None'}",
            on_clicked=lambda *_: self._toggle_todo_completion(todo_id),
        )

        slot_widget.connect(
            "key-press-event",
            lambda widget, event, tid=todo_id: self._on_slot_key_press(
                widget, event, tid
            ),
        )

        slot_info = {
            "widget": slot_widget,
            "title_label": title_label,
            "description_label": description_label,
            "tags_label": tags_label,
            "todo_id": todo_id,
            "todo": todo,
        }
        self.current_slots.append(slot_info)
        self.handler.slot_ready(slot_widget, "todos")

    def _toggle_todo_completion(self, todo_id: int) -> None:
        result = self.todo_service.get_todo(todo_id)
        if not result["success"]:
            self._show_error_message(f"Failed to get todo: {result['error']}")
            return

        todo = result["data"]
        current_status = todo.get("status", "pending")

        result = (
            self.todo_service.mark_pending(todo_id)
            if current_status == "completed"
            else self.todo_service.mark_done(todo_id)
        )
        if not result["success"]:
            self._show_error_message(f"Failed to update todo: {result['error']}")
            return

        self._refresh_todo_list()

    def _remove_todo(self, todo_id: int) -> None:
        result = self.todo_service.remove_todo(todo_id)
        if not result["success"]:
            self._show_error_message(f"Failed to remove todo: {result['error']}")
            return

        self._refresh_todo_list()

    def _on_slot_key_press(self, widget, event, todo_id: int) -> bool:
        if not event:
            return False

        # Shift+Enter: Toggle completion
        if (
            event.keyval == Gdk.KEY_Return or event.keyval == Gdk.KEY_KP_Enter
        ) and event.state & Gdk.ModifierType.SHIFT_MASK:
            return self._toggle_todo_completion(todo_id) or True

        # Alt+Enter: Remove todo
        if (
            event.keyval == Gdk.KEY_Return or event.keyval == Gdk.KEY_KP_Enter
        ) and event.state & Gdk.ModifierType.MOD1_MASK:
            return self._remove_todo(todo_id) or True

        return False

    def _handle_add_command(self, text: str) -> None:
        if not text.strip().endswith(";"):
            self._show_error_message(
                "Todo command must end with ';'\n\nUsage: add title [-d description] [-p low|medium|high];"
            )
            return

        command_text = text.strip()[:-1]
        parts = command_text.split()

        if len(parts) < 2:
            self._show_command_help("add")
            return

        title = parts[1]
        description = ""
        priority = "medium"  # Default priority

        i = 2
        while i < len(parts):
            if parts[i] == "-d":
                desc_parts = []
                i += 1
                while i < len(parts) and not parts[i].startswith("-"):
                    desc_parts.append(parts[i])
                    i += 1
                description = " ".join(desc_parts)
            elif parts[i] == "-p":
                if i + 1 < len(parts) and parts[i + 1] in ["low", "medium", "high"]:
                    priority = parts[i + 1]
                    i += 2
                else:
                    self._show_error_message(
                        "Invalid priority. Use: low, medium, or high"
                    )
                    return
            else:
                if not description:
                    desc_parts = []
                    while i < len(parts) and not parts[i].startswith("-"):
                        desc_parts.append(parts[i])
                        i += 1
                    description = " ".join(desc_parts)
                else:
                    i += 1

        result = self.todo_service.add_todo(title, description, priority=priority)
        if not result["success"]:
            self._show_error_message(f"Error adding todo: {result['error']}")
            return

        if hasattr(self.handler, "clear_input"):
            self.handler.clear_input()
        self._refresh_todo_list()

    def _handle_done_command(self, text: str) -> None:
        if text.strip() == "done":
            self._load_and_display_todos("")
            return

        if not text.strip().endswith(";"):
            self._show_error_message(
                "Todo command must end with ';'\n\nUsage: done todo_title;"
            )
            return

        command_text = text.strip()[:-1]
        parts = command_text.split()

        if len(parts) < 2:
            self._load_and_display_todos("")
            return

        todo_title = " ".join(parts[1:])
        self._execute_todo_command("mark_done", todo_title)

    def _handle_remove_command(self, text: str) -> None:
        if text.strip() == "remove":
            self._load_and_display_todos("")
            return

        if not text.strip().endswith(";"):
            self._show_error_message(
                "Todo command must end with ';'\n\nUsage: remove todo_title;"
            )
            return

        command_text = text.strip()[:-1]
        parts = command_text.split()

        if len(parts) < 2:
            self._load_and_display_todos("")
            return

        todo_title = " ".join(parts[1:])
        self._execute_todo_command("remove_todo", todo_title)

    def _handle_edit_command(self, text: str) -> None:
        if text.strip() == "edit":
            self._load_and_display_todos("")
            return

        if not text.strip().endswith(";"):
            self._show_error_message(
                "Todo command must end with ';'\n\nUsage: edit todo_title field new_value;"
            )
            return

        command_text = text.strip()[:-1]
        parts = command_text.split()

        if len(parts) < 4:
            self._load_and_display_todos("")
            return

        field = parts[-2]
        new_value = parts[-1]
        todo_title = " ".join(parts[1:-2])

        if not todo_title:
            self._show_error_message("Todo title cannot be empty")
            return

        if field not in ["title", "description", "priority", "status"]:
            self._show_error_message(
                "Invalid field. Use: title, description, priority, or status"
            )
            return

        result = self.todo_service.edit_todo(
            self._find_todo_by_title(todo_title), **{field: new_value}
        )
        if not result["success"]:
            self._show_error_message(f"Error editing todo: {result['error']}")
            return

        if hasattr(self.handler, "clear_input"):
            self.handler.clear_input()
        self._refresh_todo_list()

    def _handle_clear_command(self, text: str) -> None:
        result = self.todo_service.clear_completed()
        if not result["success"]:
            self._show_error_message(
                f"Error clearing completed todos: {result['error']}"
            )
            return

        if hasattr(self.handler, "clear_input"):
            self.handler.clear_input()
        self._refresh_todo_list()

    def _execute_todo_command(self, command: str, todo_title: str) -> None:
        todo_id = self._find_todo_by_title(todo_title)
        if not todo_id:
            return

        result = getattr(self.todo_service, command)(todo_id)
        if not result["success"]:
            self._show_error_message(f"Error executing command: {result['error']}")
            return

        if hasattr(self.handler, "clear_input"):
            self.handler.clear_input()
        self._refresh_todo_list()

    def _find_todo_by_title(self, todo_title: str) -> int:
        todos = self.todo_service.list_todos()["data"]
        matching_todos = [
            todo
            for todo in todos
            if todo.get("title", "").lower() == todo_title.lower()
        ]

        if not matching_todos:
            self._show_error_message(f"No todo found with title: '{todo_title}'")
            return None

        if len(matching_todos) > 1:
            self._show_error_message(
                f"Multiple todos found with title: '{todo_title}'\nPlease be more specific"
            )
            return None

        return matching_todos[0]["id"]

    def _show_command_help(self, command: str = None) -> None:
        help_texts = {
            "add": "Usage: add title [-d description] [-p low|medium|high];\nExample: add Buy groceries -d Get milk and bread -p high;\nExample: add Call mom -p low;\nExample: add Fix bug -d Critical issue;",
            "done": "Usage: done todo_title;\nExample: done Buy groceries;",
            "remove": "Usage: remove todo_title;\nExample: remove Buy groceries;",
            "edit": "Usage: edit todo_title field new_value;\nFields: title, description, priority, status\nExample: edit Buy groceries title Buy organic groceries;",
            "clear": "Usage: clear\nRemoves all completed todos",
        }

        help_text = help_texts.get(
            command,
            """Available commands:
• add title [-d description] [-p low|medium|high]; - Add new todo
• done todo_title; - Mark todo as completed
• remove todo_title; - Remove todo
• edit todo_title field new_value; - Edit todo
• clear - Remove all completed todos
• help - Show this help

Note: Commands with arguments must end with semicolon (;)
Flags: -d for description, -p for priority (low|medium|high)
Click on todo or Shift+Enter to toggle completion
Alt+Enter to remove todo""",
        )

        self.handler.slot_ready(
            Button(
                style_classes="app-slot todo-help",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Label(
                            label=help_text,
                            style_classes="todo-help-text",
                            h_align="center",
                        ),
                    ],
                ),
            ),
            "todos",
        )
        self.handler.done()

    def _show_error_message(self, message: str) -> None:
        self.handler.slot_ready(
            Button(
                style_classes="app-slot todo-error",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Label(
                            label=message,
                            style_classes="todo-error-text",
                            h_align="center",
                        ),
                    ],
                ),
                on_clicked=lambda *_: self.handler.launched(),
            ),
            "todos",
        )
        self.handler.done()

    def _refresh_todo_list(self) -> None:
        self.current_slots.clear()
        if hasattr(self.handler, "clear_viewport"):
            self.handler.clear_viewport()
        idle_add(self._show_todo_list)

    def _show_todo_list(self) -> None:
        self.handler.start("todos")
        self._load_and_display_todos("")

    def handle_external(self, command: str, args: str) -> None:
        # Map external commands if needed
        pass
