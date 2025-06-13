"""
Plugin system for the launcher module.
Allows extending search functionality with different content types.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class LauncherPlugin(ABC):
    """Base class for launcher plugins"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the plugin"""
        pass

    @property
    @abstractmethod
    def category(self) -> str:
        """Category this plugin belongs to"""
        pass

    @property
    def icon_name(self) -> str:
        """Icon name for this plugin's category"""
        return "application-x-executable-symbolic"

    @abstractmethod
    def search(self, query: str) -> List[Dict[str, Any]]:
        """
        Search for items matching the query

        Returns a list of dictionaries with at least:
        - title: str
        - description: str
        - icon_name: str (optional)
        - action: callable
        """
        pass

    def get_action_items(self, query: str) -> List[Dict[str, Any]]:
        """
        Get quick action items for the query

        Returns a list of dictionaries with at least:
        - title: str
        - icon_name: str
        - action: callable
        """
        return []
