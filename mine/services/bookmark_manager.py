import json
from datetime import datetime
from pathlib import Path
from typing import Any

from fabric.utils import logger

import config.data as data


class BookmarkManager:
    """Bookmark manager service for storing and managing bookmarks"""

    def __init__(self, bookmarks_file: str | None = None):
        if bookmarks_file:
            self.bookmarks_file = Path(bookmarks_file)
        else:
            self.bookmarks_file = Path(data.plugins) / "bookmarks.json"
        self._initialize_bookmarks_file()

    def _initialize_bookmarks_file(self):
        if not self.bookmarks_file.exists():
            with open(self.bookmarks_file, "w") as f:
                json.dump({}, f)

    def add_bookmark(
        self,
        name: str,
        content: str,
    ) -> dict[str, Any]:
        bookmarks = self._load_bookmarks()

        if name in bookmarks:
            return {
                "success": False,
                "error": f"Bookmark '{name}' already exists",
            }

        bookmarks[name] = {
            "content": content.strip(),
            "created_at": self._get_timestamp(),
            "updated_at": self._get_timestamp(),
        }

        self._save_bookmarks(bookmarks)
        return {
            "success": True,
            "message": f"Bookmark '{name}' added successfully",
        }

    def get_bookmark(self, name: str) -> dict[str, Any]:
        bookmarks = self._load_bookmarks()
        if name not in bookmarks:
            return {"success": False, "error": f"Bookmark '{name}' not found"}
        return {"success": True, "data": bookmarks[name]}

    def update_bookmark(self, name: str, **kwargs) -> dict[str, Any]:
        bookmarks = self._load_bookmarks()
        if name not in bookmarks:
            return {"success": False, "error": f"Bookmark '{name}' not found"}

        for field, value in kwargs.items():
            if field == "content":
                bookmarks[name][field] = value.strip()
            else:
                logger.warning(f"Unknown field '{field}' ignored")

        bookmarks[name]["updated_at"] = self._get_timestamp()
        self._save_bookmarks(bookmarks)
        return {
            "success": True,
            "message": f"Bookmark '{name}' updated successfully",
        }

    def delete_bookmark(self, name: str) -> dict[str, Any]:
        bookmarks = self._load_bookmarks()
        if name not in bookmarks:
            return {"success": False, "error": f"Bookmark '{name}' not found"}

        del bookmarks[name]
        self._save_bookmarks(bookmarks)
        return {
            "success": True,
            "message": f"Bookmark '{name}' deleted successfully",
        }

    def list_bookmarks(self) -> dict[str, Any]:
        bookmarks = self._load_bookmarks()
        return {"success": True, "data": bookmarks, "count": len(bookmarks)}

    def search_bookmarks(self, query: str) -> dict[str, Any]:
        bookmarks = self._load_bookmarks()
        query_lower = query.lower()

        matches = {}
        for name, bookmark in bookmarks.items():
            searchable_text = f"{name} {bookmark.get('content', '')}".lower()

            if query_lower in searchable_text:
                matches[name] = bookmark

        return {"success": True, "data": matches, "count": len(matches), "query": query}

    def _load_bookmarks(self) -> dict[str, Any]:
        try:
            with open(self.bookmarks_file) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Error loading bookmarks file: {e}")
            return {}

    def _save_bookmarks(self, bookmarks: dict[str, Any]):
        with open(self.bookmarks_file, "w") as f:
            json.dump(bookmarks, f, indent=2)

    def _get_timestamp(self) -> str:
        return datetime.now().isoformat()
