import json
from datetime import datetime
from pathlib import Path
from typing import Any

from fabric import Service, Signal

import config.data as data


class TodoService(Service):
    """Service to manage todo items with CRUD operations"""

    @Signal
    def todo_changed(self) -> None:
        """Signal emitted when todo list changes."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, todos_file: str | None = None, **kwargs):
        super().__init__(**kwargs)
        if todos_file:
            self.todos_file = Path(todos_file)
        else:
            self.todos_file = Path(data.plugins) / "todos.json"
        self._initialize_todos_file()

    def _initialize_todos_file(self):
        self.todos_file.touch()
        if self.todos_file.stat().st_size == 0:
            with open(self.todos_file, "w") as f:
                json.dump([], f)

    def _load_todos(self) -> list[dict[str, Any]]:
        with open(self.todos_file) as f:
            return json.load(f)

    def _save_todos(self, todos: list[dict[str, Any]]) -> None:
        with open(self.todos_file, "w") as f:
            json.dump(todos, f, indent=2)

    def _get_timestamp(self) -> str:
        return datetime.now().isoformat()

    def _get_next_id(self, todos: list[dict[str, Any]]) -> int:
        return max((todo.get("id", 0) for todo in todos), default=0) + 1

    def add_todo(
        self,
        title: str,
        description: str = "",
        priority: str = "medium",
        due_date: str | None = None,
        tags: list[str] = None,
    ) -> dict[str, Any]:
        if not title or not title.strip():
            return {"success": False, "error": "Todo title cannot be empty"}

        todos = self._load_todos()

        # Validate priority
        if priority not in ["low", "medium", "high"]:
            priority = "medium"

        new_todo = {
            "id": self._get_next_id(todos),
            "title": title.strip(),
            "description": description.strip() if description else "",
            "priority": priority,
            "status": "pending",
            "due_date": due_date,
            "tags": tags or [],
            "created_at": self._get_timestamp(),
            "updated_at": self._get_timestamp(),
        }

        todos.append(new_todo)
        self._save_todos(todos)
        self.emit("todo_changed")
        return {
            "success": True,
            "message": f"Todo '{title}' added successfully",
            "data": new_todo,
        }

    def mark_done(self, todo_id: int) -> dict[str, Any]:
        todos = self._load_todos()

        for todo in todos:
            if todo.get("id") == todo_id:
                if todo.get("status") == "completed":
                    return {
                        "success": False,
                        "error": f"Todo '{todo.get('title')}' is already completed",
                    }

                todo["status"] = "completed"
                todo["updated_at"] = self._get_timestamp()
                self._save_todos(todos)
                self.emit("todo_changed")
                return {
                    "success": True,
                    "message": f"Todo '{todo.get('title')}' marked as completed",
                    "data": todo,
                }

        return {"success": False, "error": f"Todo with ID {todo_id} not found"}

    def mark_pending(self, todo_id: int) -> dict[str, Any]:
        todos = self._load_todos()

        for todo in todos:
            if todo.get("id") == todo_id:
                if todo.get("status") == "pending":
                    return {
                        "success": False,
                        "error": f"Todo '{todo.get('title')}' is already pending",
                    }

                todo["status"] = "pending"
                todo["updated_at"] = self._get_timestamp()
                self._save_todos(todos)
                self.emit("todo_changed")
                return {
                    "success": True,
                    "message": f"Todo '{todo.get('title')}' marked as pending",
                    "data": todo,
                }

        return {"success": False, "error": f"Todo with ID {todo_id} not found"}

    def remove_todo(self, todo_id: int) -> dict[str, Any]:
        todos = self._load_todos()

        for i, todo in enumerate(todos):
            if todo.get("id") == todo_id:
                removed_todo = todos.pop(i)
                self._save_todos(todos)
                self.emit("todo_changed")
                return {
                    "success": True,
                    "message": f"Todo '{removed_todo.get('title')}' removed successfully",
                    "data": removed_todo,
                }

        return {"success": False, "error": f"Todo with ID {todo_id} not found"}

    def edit_todo(self, todo_id: int, **kwargs) -> dict[str, Any]:
        todos = self._load_todos()

        for todo in todos:
            if todo.get("id") == todo_id:
                if "title" in kwargs:
                    new_title = kwargs["title"]
                    if not new_title or not new_title.strip():
                        return {"success": False, "error": "Todo title cannot be empty"}
                    todo["title"] = new_title.strip()

                if "description" in kwargs:
                    todo["description"] = (
                        kwargs["description"].strip() if kwargs["description"] else ""
                    )

                if "priority" in kwargs and kwargs["priority"] in [
                    "low",
                    "medium",
                    "high",
                ]:
                    todo["priority"] = kwargs["priority"]

                if "due_date" in kwargs:
                    todo["due_date"] = kwargs["due_date"]

                if "tags" in kwargs:
                    todo["tags"] = kwargs["tags"] or []

                if "status" in kwargs and kwargs["status"] in ["pending", "completed"]:
                    todo["status"] = kwargs["status"]

                todo["updated_at"] = self._get_timestamp()
                self._save_todos(todos)
                self.emit("todo_changed")
                return {
                    "success": True,
                    "message": f"Todo '{todo.get('title')}' updated successfully",
                    "data": todo,
                }

        return {"success": False, "error": f"Todo with ID {todo_id} not found"}

    def get_todo(self, todo_id: int) -> dict[str, Any]:
        todos = self._load_todos()

        for todo in todos:
            if todo.get("id") == todo_id:
                return {"success": True, "data": todo}

        return {"success": False, "error": f"Todo with ID {todo_id} not found"}

    def list_todos(
        self,
        status: str | None = None,
        priority: str | None = None,
        tag: str | None = None,
    ) -> dict[str, Any]:
        todos = self._load_todos()

        filtered_todos = [
            todo
            for todo in todos
            if (not status or todo.get("status") == status)
            and (not priority or todo.get("priority") == priority)
            and (not tag or tag in todo.get("tags", []))
        ]

        return {
            "success": True,
            "data": filtered_todos,
            "count": len(filtered_todos),
            "total": len(todos),
        }

    def search_todos(self, query: str) -> dict[str, Any]:
        todos = self._load_todos()
        query_lower = query.lower()

        matches = [
            todo
            for todo in todos
            if query_lower in todo.get("title", "").lower()
            or query_lower in todo.get("description", "").lower()
        ]

        return {"success": True, "data": matches, "count": len(matches), "query": query}

    def clear_completed(self) -> dict[str, Any]:
        todos = self._load_todos()
        original_count = len(todos)

        pending_todos = [todo for todo in todos if todo.get("status") != "completed"]
        removed_count = original_count - len(pending_todos)

        self._save_todos(pending_todos)
        self.emit("todo_changed")
        return {
            "success": True,
            "message": f"Removed {removed_count} completed todos",
            "removed_count": removed_count,
        }

    def get_stats(self) -> dict[str, Any]:
        todos = self._load_todos()
        total = len(todos)
        pending = len([todo for todo in todos if todo.get("status") == "pending"])
        completed = len([todo for todo in todos if todo.get("status") == "completed"])

        priority_stats = {
            "low": len([todo for todo in todos if todo.get("priority") == "low"]),
            "medium": len([todo for todo in todos if todo.get("priority") == "medium"]),
            "high": len([todo for todo in todos if todo.get("priority") == "high"]),
        }

        return {
            "success": True,
            "data": {
                "total": total,
                "pending": pending,
                "completed": completed,
                "completion_rate": (completed / total * 100) if total > 0 else 0,
                "priority_stats": priority_stats,
            },
        }
