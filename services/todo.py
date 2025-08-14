# Standard library imports
import json
import uuid
from datetime import datetime
from pathlib import Path

# Fabric imports
from fabric.core.service import Property, Service

# Local imports
import config.data as data


class TodoService(Service):
    """Service for managing persistent todo list with JSON storage"""

    def __init__(self):
        super().__init__()
        self._todos = []
        self._file_path = self._get_todos_file_path()
        self._load_todos()
        self._callbacks = []

    def add_callback(self, callback):
        """Add a callback function to be notified of changes"""
        self._callbacks.append(callback)

    def remove_callback(self, callback):
        """Remove a callback function"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def _notify_callbacks(self, event_type, data=None):
        """Notify all registered callbacks of changes"""
        for callback in self._callbacks:
            try:
                callback(event_type, data)
            except Exception as e:
                print(f"Error in todo callback: {e}")

    def _get_todos_file_path(self):
        """Returns the path to the todos JSON file"""
        cache_dir = Path(data.CACHE_DIR) / "todos"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / "todos.json"

    def _load_todos(self):
        """Load todos from JSON file"""
        try:
            if self._file_path.exists():
                with open(self._file_path, "r", encoding="utf-8") as f:
                    self._todos = json.load(f)
            else:
                self._todos = []
        except Exception as e:
            print(f"Error loading todos: {e}")
            self._todos = []

    def _save_todos(self):
        """Save todos to JSON file"""
        try:
            with open(self._file_path, "w", encoding="utf-8") as f:
                json.dump(self._todos, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving todos: {e}")

    @Property(list, "readable")
    def todos(self):
        """Get all todos"""
        return self._todos.copy()

    def add_todo(self, text: str, priority: str = "medium") -> dict:
        """Add a new todo item"""
        todo = {
            "id": str(uuid.uuid4()),
            "text": text,
            "completed": False,
            "priority": priority,  # low, medium, high
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        self._todos.append(todo)
        self._save_todos()
        self._notify_callbacks("todo-added", todo)
        self._notify_callbacks("todos-changed")
        return todo

    def delete_todo(self, todo_id: str) -> bool:
        """Delete a todo item by ID"""
        for i, todo in enumerate(self._todos):
            if todo["id"] == todo_id:
                deleted_todo = self._todos.pop(i)
                self._save_todos()
                self._notify_callbacks("todo-deleted", deleted_todo)
                self._notify_callbacks("todos-changed")
                return True
        return False

    def toggle_todo(self, todo_id: str) -> bool:
        """Toggle completion status of a todo item"""
        for todo in self._todos:
            if todo["id"] == todo_id:
                todo["completed"] = not todo["completed"]
                todo["updated_at"] = datetime.now().isoformat()
                self._save_todos()
                self._notify_callbacks("todo-toggled", todo)
                self._notify_callbacks("todos-changed")
                return True
        return False

    def edit_todo(self, todo_id: str, new_text: str) -> bool:
        """Edit the text of a todo item"""
        for todo in self._todos:
            if todo["id"] == todo_id:
                todo["text"] = new_text
                todo["updated_at"] = datetime.now().isoformat()
                self._save_todos()
                self._notify_callbacks("todo-edited", todo)
                self._notify_callbacks("todos-changed")
                return True
        return False

    def set_priority(self, todo_id: str, priority: str) -> bool:
        """Set the priority of a todo item"""
        if priority not in ["low", "medium", "high"]:
            return False

        for todo in self._todos:
            if todo["id"] == todo_id:
                todo["priority"] = priority
                todo["updated_at"] = datetime.now().isoformat()
                self._save_todos()
                self._notify_callbacks("todo-priority-changed", todo)
                self._notify_callbacks("todos-changed")
                return True
        return False

    def get_todo(self, todo_id: str) -> dict | None:
        """Get a specific todo by ID"""
        for todo in self._todos:
            if todo["id"] == todo_id:
                return todo.copy()
        return None

    def clear_completed(self):
        """Remove all completed todos"""
        initial_count = len(self._todos)
        self._todos = [todo for todo in self._todos if not todo["completed"]]
        if len(self._todos) < initial_count:
            self._save_todos()
            self._notify_callbacks("todos-changed")

    def get_stats(self) -> dict:
        """Get todo statistics"""
        total = len(self._todos)
        completed = sum(1 for todo in self._todos if todo["completed"])
        pending = total - completed

        return {
            "total": total,
            "completed": completed,
            "pending": pending,
            "completion_rate": (completed / total * 100) if total > 0 else 0,
        }


# Global service instance
todo_service = TodoService()

