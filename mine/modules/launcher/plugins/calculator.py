from fabric.utils import exec_shell_command, exec_shell_command_async
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label

from modules.launcher.base import LauncherPlugin


class CalculatorPlugin(LauncherPlugin):
    @property
    def name(self) -> str:
        return "calculator"

    @property
    def icon(self) -> str:
        return "calculator"

    @property
    def keywords(self) -> list[str]:
        return ["calc"]

    def on_search(self, text: str) -> None:
        self.query_calc(text)

    def stop(self):
        pass

    def query_calc(self, text: str) -> None:
        if not text.strip():
            return self.handler.done()

        self.handler.start("calc")

        result = exec_shell_command(f"qalc -t '{text}'")
        if result and result.strip():
            if " = " in result:
                answer = result.split(" = ")[-1].strip()
            else:
                answer = result.strip()
            self.handler.slot_ready(
                Button(
                    style_classes="app-slot calc-result",
                    child=Box(
                        orientation="v",
                        spacing=8,
                        children=[
                            Label(
                                label=f"{text} =",
                                style_classes="calc-expression",
                                h_align="start",
                            ),
                            Label(
                                label=answer,
                                style_classes="calc-result-text",
                                h_align="start",
                            ),
                        ],
                    ),
                    on_clicked=lambda *_: exec_shell_command_async(f"qalc '{text}'"),
                ),
                "calc",
            )

        self.handler.done()
