"""
Result class representing a search result from plugins.
"""

from typing import Optional, Callable, Any
from dataclasses import dataclass
from gi.repository import GdkPixbuf
import utils.icons as icons


@dataclass
class Result:
    """
    Represents a search result that can be displayed and activated.
    """
    
    # Display information
    title: str
    subtitle: str = ""
    description: str = ""
    icon: Optional[GdkPixbuf.Pixbuf] = None
    icon_name: Optional[str] = None
    icon_markup: Optional[str] = None
    # Behavior
    action: Optional[Callable[[], Any]] = None
    relevance: float = 0.0
    
    # Metadata
    plugin_name: str = ""
    data: Optional[dict] = None
    
    def activate(self):
        """Activate this result (execute its action)."""
        if self.action:
            return self.action()
        else:
            raise NotImplementedError("No action defined for this result")
            
    def __post_init__(self):
        """Post-initialization processing."""
        # Ensure relevance is within valid range
        self.relevance = max(0.0, min(1.0, self.relevance))
        
        # Set default data if None
        if self.data is None:
            self.data = {}
            
    def __str__(self):
        return f"Result(title='{self.title}', relevance={self.relevance})"
        
    def __repr__(self):
        return self.__str__()
