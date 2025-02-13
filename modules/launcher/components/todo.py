import json
import os

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow
from snippets import MaterialIcon


class TodoManager(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="todo-launcher",
            all_visible=False,
            visible=False,
            **kwargs,
        )

        self._arranger_handler = 0
        self.todo_manager = TodoListManager(self)
        self.viewport = None

        self.todo_entry = Entry(
            name="todo-entry",
            h_expand=True,
            on_activate=lambda entry, *_: self.handle_add_todo(entry.get_text()),
        )

        self.header_box = Box(
            name="header-box",
            spacing=10,
            orientation="h",
            children=[
                self.todo_entry,
                Button(
                    name="add-button",
                    child=MaterialIcon("add"),
                    tooltip_text="Add Todo",
                    on_clicked=lambda *_: self.handle_add_todo(
                        self.todo_entry.get_text()
                    ),
                ),
            ],
        )

        self.launcher_box = Box(
            name="todo-launcher-box",
            spacing=10,
            orientation="v",
            h_expand=True,
            children=[self.header_box],
        )

        self.add(self.launcher_box)

    def open_launcher(self):
        if not self.viewport:
            self.viewport = Box(name="viewport", spacing=4, orientation="v")
            self.scrolled_window = ScrolledWindow(
                name="todo-content",
                spacing=10,
                h_scrollbar_policy="never",
                child=self.viewport,
            )
            self.launcher_box.add(self.scrolled_window)

        self.viewport.children = []
        self.todo_manager.arrange_viewport()

        self.viewport.show()
        self.todo_entry.grab_focus()

    def handle_add_todo(self, text: str):
        if text.strip():
            self.todo_manager.add_todo(text)
            self.todo_entry.set_text("")


class TodoListManager:
    def __init__(self, launcher):
        self.launcher = launcher
        self.todos = []
        self.todo_file = os.path.expanduser("~/.local/share/fabric/todos.json")
        self.load_todos()

    def load_todos(self):
        os.makedirs(os.path.dirname(self.todo_file), exist_ok=True)
        try:
            if os.path.exists(self.todo_file):
                with open(self.todo_file, "r") as f:
                    self.todos = json.load(f)
        except Exception as e:
            print(f"Error loading todos: {e}")
            self.todos = []

    def save_todos(self):
        try:
            with open(self.todo_file, "w") as f:
                json.dump(self.todos, f)
        except Exception as e:
            print(f"Error saving todos: {e}")

    def add_todo(self, content: str):
        todo = {"content": content, "completed": False, "id": len(self.todos)}
        self.todos.append(todo)
        self.save_todos()
        self.arrange_viewport()

    def toggle_todo(self, todo_id: int):
        for todo in self.todos:
            if todo["id"] == todo_id:
                todo["completed"] = not todo["completed"]
                break
        self.save_todos()
        self.arrange_viewport()

    def delete_todo(self, todo_id: int):
        self.todos = [todo for todo in self.todos if todo["id"] != todo_id]
        self.save_todos()
        self.arrange_viewport()

    def bake_todo_slot(self, todo: dict) -> Box:
        todo_box = Box(
            name="todo-item",
            spacing=10,
            orientation="h",
            h_expand=True,
        )

        checkbox = Button(
            name="todo-checkbox",
            child=MaterialIcon(
                "check_box" if todo["completed"] else "check_box_outline_blank"
            ),
            on_clicked=lambda _, todo_id=todo["id"]: self.toggle_todo(todo_id),
        )

        label = Label(
            label=todo["content"],
            h_expand=True,
            v_align="center",
            h_align="start",
            name="todo-label-completed" if todo["completed"] else "todo-label",
        )

        delete_button = Button(
            name="delete-button",
            child=MaterialIcon("delete"),
            on_clicked=lambda _, todo_id=todo["id"]: self.delete_todo(todo_id),
        )

        todo_box.add(checkbox)
        todo_box.add(label)
        todo_box.add(delete_button)

        return todo_box

    def arrange_viewport(self):
        if not self.launcher.viewport:
            return

        self.launcher.viewport.children = []

        for todo in self.todos:
            todo_slot = self.bake_todo_slot(todo)
            self.launcher.viewport.add(todo_slot)
