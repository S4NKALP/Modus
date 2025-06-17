"""
Base class for launcher plugins.
"""

from abc import ABC, abstractmethod
from typing import List
from .result import Result


class PluginBase(ABC):
    """
    Abstract base class for launcher plugins.
    All plugins must inherit from this class.
    """
    
    def __init__(self):
        self.name = self.__class__.__name__.lower()
        self.display_name = self.__class__.__name__
        self.description = "A launcher plugin"
        self.version = "1.0.0"
        self.enabled = True
        self._triggers = []  # List of trigger keywords
        
    @abstractmethod
    def initialize(self):
        """
        Initialize the plugin.
        Called when the plugin is activated.
        """
        pass
        
    @abstractmethod
    def cleanup(self):
        """
        Cleanup the plugin.
        Called when the plugin is deactivated.
        """
        pass
        
    @abstractmethod
    def query(self, query_string: str) -> List[Result]:
        """
        Process a search query and return results.
        
        Args:
            query_string: The search query from the user
            
        Returns:
            List of Result objects
        """
        pass
        
    def get_triggers(self) -> List[str]:
        """
        Get list of trigger keywords for this plugin.
        If the query starts with any of these, this plugin gets priority.

        Returns:
            List of trigger strings (e.g., ["calc", "=", "math"])
        """
        return self._triggers

    def set_triggers(self, triggers: List[str]):
        """
        Set the trigger keywords for this plugin.

        Args:
            triggers: List of trigger keywords
        """
        self._triggers = triggers
        
    def handles_query(self, query_string: str) -> bool:
        """
        Check if this plugin should handle the given query.

        Args:
            query_string: The search query

        Returns:
            True if this plugin should process the query
        """
        if not self.enabled:
            return False

        # Check triggers
        triggers = self.get_triggers()
        if triggers:
            query_lower = query_string.lower().strip()
            return any(query_lower.startswith(trigger.lower()) for trigger in triggers)

        # Default: handle all queries
        return True

    def get_active_trigger(self, query_string: str) -> str:
        """
        Get the active trigger for the given query.

        Args:
            query_string: The search query

        Returns:
            The trigger keyword if found, empty string otherwise
        """
        if not self.enabled:
            return ""

        triggers = self.get_triggers()
        if triggers:
            query_lower = query_string.lower().strip()

            # Sort triggers by length (longest first) to match more specific triggers first
            sorted_triggers = sorted(triggers, key=len, reverse=True)

            for trigger in sorted_triggers:
                trigger_lower = trigger.lower()

                # Exact match with trigger (including space if present)
                if query_lower.startswith(trigger_lower):
                    return trigger

                # Match trigger word followed by space
                trigger_word = trigger.strip().lower()
                if (query_lower.startswith(trigger_word + " ") or
                    query_lower == trigger_word):
                    return trigger

        return ""

    def query_triggered(self, query_string: str, trigger: str) -> List[Result]:
        """
        Process a triggered query (when plugin is in sticky mode).
        Default implementation removes trigger and calls query().

        Args:
            query_string: The full query string including trigger
            trigger: The trigger that activated this plugin

        Returns:
            List of Result objects
        """
        # Remove trigger from query and process remaining text
        remaining_query = query_string[len(trigger):].strip()
        return self.query(remaining_query)
        
    def get_config(self) -> dict:
        """
        Get plugin configuration.
        
        Returns:
            Dictionary of configuration options
        """
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "version": self.version,
            "enabled": self.enabled,
        }
        
    def set_config(self, config: dict):
        """
        Set plugin configuration.
        
        Args:
            config: Dictionary of configuration options
        """
        self.enabled = config.get("enabled", self.enabled)
        
    def __str__(self):
        return f"Plugin({self.name})"
        
    def __repr__(self):
        return self.__str__()
