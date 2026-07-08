from __future__ import annotations

import math
from typing import TYPE_CHECKING, List, Tuple

from .constants import (
    BG_PADDING_H,
    BG_PADDING_V,
    ICON_GAP,
    INDICATOR_H,
    MAX_SCALE,
    MIN_SCALE,
    SIGMA_FACTOR,
)

if TYPE_CHECKING:
    from .canvas import DockItem


class DockLayout:
    @staticmethod
    def compute(
        items: List[DockItem],
        mouse_x: float,
        mouse_y: float,
        base_icon_size: int,
        canvas_w: int,
        canvas_h: int,
        mouse_inside: bool,
    ) -> None:
        if not items:
            return

        sigma = base_icon_size * SIGMA_FACTOR
        amplitude = MAX_SCALE - MIN_SCALE

        n = len(items)
        base_w = base_icon_size + ICON_GAP
        total_base = n * base_icon_size + max(n - 1, 0) * ICON_GAP
        start_x = (canvas_w - total_base) / 2.0

        for i, item in enumerate(items):
            est_cx = start_x + i * base_w + base_icon_size / 2.0

            if mouse_inside:
                dist = abs(est_cx - mouse_x)
                target = MIN_SCALE + amplitude * math.exp(
                    -(dist * dist) / (2.0 * sigma * sigma)
                )
            else:
                target = MIN_SCALE

            item.target_scale = target

        bg_h = base_icon_size + 2 * BG_PADDING_V
        bg_y = canvas_h - INDICATOR_H - bg_h
        baseline_y = bg_y + BG_PADDING_V + base_icon_size

        rendered_widths = [base_icon_size * item.current_scale for item in items]
        total_w = sum(rendered_widths) + max(n - 1, 0) * ICON_GAP
        cursor_x = (canvas_w - total_w) / 2.0

        for i, item in enumerate(items):
            iw = rendered_widths[i]
            ih = base_icon_size * item.current_scale
            ix = cursor_x
            iy = baseline_y - ih
            item.render_x = ix
            item.render_y = iy
            item.render_w = iw
            item.render_h = ih
            item.drag_index = i
            cursor_x += iw + ICON_GAP

    @staticmethod
    def background_rect(
        items: List[DockItem],
        base_icon_size: int,
        canvas_w: int,
        canvas_h: int,
    ) -> Tuple[float, float, float, float]:
        bg_h = base_icon_size + 2 * BG_PADDING_V
        bg_y = canvas_h - INDICATOR_H - bg_h

        if items:
            min_x = min(item.render_x for item in items)
            max_x = max(item.render_x + item.render_w for item in items)
            bg_x = min_x - BG_PADDING_H
            bg_w = (max_x - min_x) + 2 * BG_PADDING_H
        else:
            bg_x = BG_PADDING_H
            bg_w = canvas_w - 2 * BG_PADDING_H

        return bg_x, bg_y, bg_w, bg_h
