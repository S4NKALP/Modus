from fabric.widgets.button import Button
from utils.utils import svg_file


class ToolButton(Button):
    """A toggle button representing one capture/record mode."""

    def __init__(self, icon: str, tooltip: str, tool_id: str, group, **kwargs):
        self.tool_id = tool_id
        self._group = group

        img = svg_file(f"screencapture/{icon}", size=20)

        super().__init__(
            name="sc-tool-btn",
            tooltip_text=tooltip,
            child=img,
            **kwargs,
        )
        self.connect("clicked", self._on_clicked)

    def _on_clicked(self, *_):
        self._group.select(self)

    def set_active(self, active: bool):
        ctx = self.get_style_context()
        if active:
            ctx.add_class("active")
        else:
            ctx.remove_class("active")


class ToolGroup:
    """Manages exclusive selection among ToolButtons."""

    def __init__(self):
        self._buttons: list[ToolButton] = []
        self._selected: ToolButton | None = None
        self._callbacks: list = []

    def add(self, btn: ToolButton):
        self._buttons.append(btn)

    def select(self, btn: ToolButton):
        if self._selected is btn:
            return
        if self._selected:
            self._selected.set_active(False)
        self._selected = btn
        btn.set_active(True)
        for cb in self._callbacks:
            cb(btn.tool_id)

    def select_index(self, idx: int):
        if 0 <= idx < len(self._buttons):
            self.select(self._buttons[idx])

    def select_id(self, tool_id: str):
        for btn in self._buttons:
            if btn.tool_id == tool_id:
                self.select(btn)
                return

    def current_index(self) -> int:
        if self._selected and self._selected in self._buttons:
            return self._buttons.index(self._selected)
        return 0

    def on_change(self, cb):
        self._callbacks.append(cb)

    @property
    def selected_id(self) -> str | None:
        return self._selected.tool_id if self._selected else None
