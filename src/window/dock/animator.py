from typing import Optional

from fabric.utils import GLib

from .constants import ANIM_INTERVAL_MS, IDLE_THRESHOLD, LERP_FACTOR
from .layout import DockLayout


class DockAnimator:
    def __init__(self, canvas):
        self._canvas = canvas
        self._timer_id: Optional[int] = None
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._timer_id = GLib.timeout_add(ANIM_INTERVAL_MS, self._tick)

    def stop(self) -> None:
        self._running = False
        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = None

    def _tick(self) -> bool:
        if not self._running:
            return False

        canvas = self._canvas
        items = canvas.model.items
        dirty = False

        for item in items:
            delta = item.target_scale - item.current_scale
            if abs(delta) > IDLE_THRESHOLD:
                item.current_scale += delta * LERP_FACTOR
                dirty = True
            else:
                item.current_scale = item.target_scale

        model_w = canvas._canvas_max_width()
        model_h = canvas._canvas_height()
        DockLayout.compute(
            items,
            canvas._mouse_x,
            canvas._mouse_y,
            canvas._base_icon_size(),
            model_w,
            model_h,
            canvas._mouse_inside,
        )

        if (
            model_w != canvas._last_requested_width
            or model_h != canvas._last_requested_height
        ):
            canvas._last_requested_width = model_w
            canvas._last_requested_height = model_h
            canvas._update_size_request()

        if dirty or canvas._needs_redraw:
            canvas._needs_redraw = False
            canvas.queue_draw()

        # Self-pause: stop ticking once nothing is animating and no redraw is
        # pending, so an idle dock consumes zero CPU. Restarted on mouse
        # motion/enter, size changes or model rebuilds.
        if not dirty and not canvas._needs_redraw:
            self._running = False
            self._timer_id = None
            return False

        return self._running
