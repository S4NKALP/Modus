import math
import re
import subprocess
import time
from typing import List

import utils.icons as icons
from modules.launcher.plugin_base import PluginBase
from modules.launcher.result import Result
from utils.conversion import Conversion


class CalculatorPlugin(PluginBase):
    """
    Plugin for calculating mathematical expressions and converting units.
    """

    def __init__(self):
        super().__init__()
        self.display_name = "Calculator"
        self.description = "Evaluate mathematical expressions and convert units"

        # Safe functions for evaluation
        self.safe_functions = {
            "abs": abs,
            "round": round,
            "min": min,
            "max": max,
            "sum": sum,
            "pow": pow,
            "sqrt": math.sqrt,
            "sin": math.sin,
            "cos": math.cos,
            "tan": math.tan,
            "asin": math.asin,
            "acos": math.acos,
            "atan": math.atan,
            "log": math.log,
            "log10": math.log10,
            "exp": math.exp,
            "pi": math.pi,
            "e": math.e,
        }

        # Initialize conversion utility
        self.converter = Conversion()

        # Pre-compiled regex patterns
        self.expression_pattern = re.compile(r"[\d+\-*/^()=]")
        self.number_pattern = re.compile(r"\d")
        self.conversion_pattern = re.compile(
            r"(\d+(?:\.\d+)?)\s*([a-zA-Z]+)\s*(?:to|in|=)\s*([a-zA-Z]+)"
        )

        # Cache for conversion results
        self._conversion_cache = {}
        self._last_cache_cleanup = time.time()
        self._cache_cleanup_interval = 300  # 5 minutes

    def initialize(self):
        """Initialize the files plugin."""
        self.set_triggers(["="])

    def _cleanup_cache(self):
        """Clean up old cache entries."""
        current_time = time.time()
        if current_time - self._last_cache_cleanup > self._cache_cleanup_interval:
            self._conversion_cache.clear()
            self._last_cache_cleanup = current_time

    def query(self, query: str) -> List[Result]:
        """Process a query and return results."""
        if not query:
            return []

        # Clean up cache periodically
        self._cleanup_cache()

        # Check if it's a conversion query
        conversion_match = self.conversion_pattern.match(query)
        if conversion_match:
            try:
                value, from_unit, to_unit = conversion_match.groups()
                value = float(value)

                # Check cache first
                cache_key = f"{value}_{from_unit}_{to_unit}"
                if cache_key in self._conversion_cache:
                    result = self._conversion_cache[cache_key]
                    subtitle = f"{value} {from_unit} = {result:.6g} {to_unit}"
                else:
                    # Use the conversion utility
                    result = self.converter.convert(value, from_unit, to_unit)
                    # Cache the result
                    self._conversion_cache[cache_key] = result
                    subtitle = f"{value} {from_unit} = {result:.6g} {to_unit}"

                return [
                    Result(
                        title=f"{result:.6g} {to_unit}",
                        subtitle=subtitle,
                        icon_markup=icons.calculator,
                        action=lambda r=f"{result:.6g}": self._copy_to_clipboard(r),
                        relevance=1.0,
                        plugin_name=self.display_name,
                        data={"from": (value, from_unit), "to": (result, to_unit)},
                    )
                ]
            except ValueError as e:
                return [
                    Result(
                        title="Invalid conversion",
                        subtitle=str(e),
                        icon_markup=icons.calculator,
                        relevance=0.0,
                        plugin_name=self.display_name,
                    )
                ]

        # Check if it's a math expression
        if self.expression_pattern.search(query):
            try:
                # Evaluate the expression
                result = eval(query, {"__builtins__": {}}, self.safe_functions)
                if isinstance(result, (int, float)):
                    return [
                        Result(
                            title=f"{result:.6g}",
                            subtitle=f"{query} = {result:.6g}",
                            icon_markup=icons.calculator,
                            action=lambda r=f"{result:.6g}": self._copy_to_clipboard(r),
                            relevance=1.0,
                            plugin_name=self.display_name,
                        )
                    ]
            except Exception:
                pass

        return []

    def _format_cache_age(self, age_seconds: float) -> str:
        """Format cache age for display."""
        if age_seconds < 60:
            return f"{int(age_seconds)}s ago"
        elif age_seconds < 3600:
            return f"{int(age_seconds // 60)}m ago"
        else:
            return f"{int(age_seconds // 3600)}h ago"

    def _copy_to_clipboard(self, text: str):
        """Copy text to clipboard using cliphist."""
        try:
            # First copy to clipboard
            subprocess.run(["wl-copy"], input=text.encode(), check=True)
            # Then store in cliphist
            subprocess.run(["cliphist", "store"], input=text.encode(), check=True)
        except subprocess.CalledProcessError:
            # If cliphist fails, at least we have the text in clipboard
            pass

    def cleanup(self):
        """Clean up resources."""
        self._conversion_cache.clear()
        self.converter.cleanup()
