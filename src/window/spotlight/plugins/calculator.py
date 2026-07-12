from typing import Any

from utils.functions import run_command, spawn_detached
from window.spotlight.api import PluginContext, SearchResult, SpotlightPlugin


class CalculatorPlugin(SpotlightPlugin):
    id = "calculator"
    name = "calculator"
    icon = "accessories-calculator-symbolic"
    keywords = ["calc"]
    searchable = True
    priority = 90

    def __init__(self, context: PluginContext) -> None:
        super().__init__(context)

    def initialize(self) -> None:
        pass

    def cleanup(self) -> None:
        pass

    def detect(self, text: str) -> bool:
        s = text.strip()
        if not s:
            return False
        has_digit = any(c.isdigit() for c in s)
        has_op = any(c in "+-*/^%()" for c in s)
        return has_digit and has_op

    def search(self, query: str, token: Any) -> list[SearchResult]:
        s = query.strip()
        if not s:
            return []

        if s.lower().startswith("calc "):
            s = s[5:].strip()
        elif s.lower() == "calc":
            return [
                SearchResult(
                    id="calc_hint",
                    title="Calculator",
                    subtitle="Type a math expression (e.g. 2+2)",
                    icon_name="accessories-calculator-symbolic",
                    score=100.0,
                    render_type="calc",
                )
            ]

        if not s:
            return []

        has_digit = any(c.isdigit() for c in s)
        has_op = any(c in "+-*/^%()" for c in s)
        if not (has_digit and has_op):
            return []

        result = self._run_qalc(s)
        if not result or not result.strip():
            return []

        if " = " in result:
            answer = result.split(" = ")[-1].strip()
        else:
            answer = result.strip()

        return [
            SearchResult(
                id=f"calc_{s}",
                title=f"{s} =",
                subtitle=answer,
                icon_name="accessories-calculator-symbolic",
                score=90.0,
                render_type="calc",
                action=lambda s=s: self._run_qalc_async(s),
                metadata={},
            )
        ]

    @staticmethod
    def _run_qalc(expression: str) -> str:
        result = run_command(["qalc", "-t", expression], timeout=10)
        if result.returncode not in [0, -1]:
            return ""
        return result.stdout or ""

    @staticmethod
    def _run_qalc_async(expression: str) -> None:
        spawn_detached(["qalc", expression])


PLUGIN = CalculatorPlugin
