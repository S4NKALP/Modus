import re
from typing import List, Dict, Any
from . import LauncherPlugin


class CalculatorPlugin(LauncherPlugin):
    """Plugin for calculator functionality"""

    @property
    def name(self) -> str:
        return "Calculator"

    @property
    def category(self) -> str:
        return "Utilities"

    @property
    def icon_name(self) -> str:
        return "accessories-calculator-symbolic"

    def search(self, query: str) -> List[Dict[str, Any]]:
        # Only process if query looks like a math expression
        if not (query.isdigit() or re.match(r"^[\d+\-*/().]+$", query)):
            return []

        try:
            result = eval(query)
            return [
                {
                    "title": f"{query} = {result}",
                    "description": "Calculator result",
                    "icon_name": "accessories-calculator-symbolic",
                    "action": lambda: None,  # No action needed
                }
            ]
        except:
            return []

    def get_action_items(self, query: str) -> List[Dict[str, Any]]:
        # Only process if query looks like a math expression
        if not (query.isdigit() or re.match(r"^[\d+\-*/().]+$", query)):
            return []

        try:
            result = eval(query)
            return [
                {
                    "title": f"Calculate: {query} = {result}",
                    "icon_name": "accessories-calculator-symbolic",
                    "action": lambda: None,  # No action needed
                }
            ]
        except:
            return []
