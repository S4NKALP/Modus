from fabric.utils import logger
from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.label import Label

from utils.gtk_utils import svg_file
from utils.timer import ManagedTimer

DISPLAY_MS = 2000  # how long each indicator stays visible (ms)


class BaseNotchIndicator(Box):
    """Shared timer + layout scaffolding for notch indicators.

    Subclasses override :meth:`_on_activate` (called when the indicator
    should become visible) and :meth:`_on_destroy` (optional extra cleanup).
    """

    def __init__(
        self,
        name: str,
        icon_name: str,
        label_text: str,
        show_cb,
        hide_cb,
        *,
        icon_size: int = 16,
        icon_first: bool = True,
        **kwargs,
    ):
        super().__init__(
            name=name,
            orientation="h",
            h_expand=True,
            v_align="center",
            **kwargs,
        )
        self._show_cb = show_cb
        self._hide_cb = hide_cb
        self._hide_timer = ManagedTimer()

        self._icon = svg_file(
            icon_name,
            size=icon_size,
            name="notch-indicator-icon",
            v_align="center",
        )
        self._label = Label(
            name="notch-indicator-label",
            label=label_text,
            v_align="center",
        )

        if icon_first:
            start, end = self._icon, self._label
        else:
            start, end = self._label, self._icon

        self.add(
            CenterBox(
                orientation="h",
                h_expand=True,
                start_children=start,
                end_children=end,
            )
        )

    def _schedule_hide(self):
        self._hide_timer.schedule(DISPLAY_MS, self._hide_cb)

    def destroy(self):
        self._hide_timer.cancel()
        try:
            self._on_destroy()
        except Exception as e:
            logger.warning(f"[NotchIndicators] {self.get_name()} destroy: {e}")
        super().destroy()

    def _on_destroy(self):
        """Override for extra signal disconnection."""
