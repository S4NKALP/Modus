from __future__ import annotations

import json
import math
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import cairo
import tomlkit
from fabric.utils import (
    Gdk,
    GdkPixbuf,
    GLib,
    Gtk,
    exec_shell_command_async,
    get_desktop_applications,
    get_relative_path,
    logger,
    os,
    random,
    re,
)
from fabric.widgets.revealer import Revealer
from fabric.widgets.wayland import WaylandWindow as Window
from gi.repository import Rsvg

from services.config import config, on_config_change
from services.modus import modus_service
from utils.functions import is_special_workspace_id
from utils.icon_resolver import IconResolver
from utils.occlusion import check_occlusion
from utils.utils import svg_file

# pinned apps config file path
PINNED_APPS_FILE = get_relative_path("../../config/dock.toml")

# Animation
LERP_FACTOR = 0.20  # per-frame interpolation speed (0–1)
IDLE_THRESHOLD = 0.0005  # stop redrawing when deltas are smaller than this
ANIM_FPS = 60
ANIM_INTERVAL_MS = 1000 // ANIM_FPS  # 16 ms

# Magnification (Gaussian)
MAX_SCALE = 2.0  # peak scale at cursor
MIN_SCALE = 1.0  # rest scale
SIGMA_FACTOR = 1.3  # sigma = base_icon_size * SIGMA_FACTOR (wider = smoother wave)

# Layout
ICON_GAP = 8  # pixels between icons (at scale 1)
BG_PADDING_H = 14  # horizontal padding inside background pill
BG_PADDING_V = 12  # vertical padding (above/below icons inside pill)
CANVAS_TOP_PAD = 28  # extra space above background for magnified icons
INDICATOR_H = 10  # height below pill for running dot
SEPARATOR_WIDTH = 1  # pixel width of separator line
SEPARATOR_GAP = 4  # gap between separator and neighbouring icons

# Visual style — macOS-inspired frosted glass
BG_RADIUS = 20.0  # background pill corner radius
BG_ALPHA = 0.82  # background fill opacity
BORDER_ALPHA = 0.50  # border stroke opacity
BORDER_WIDTH = 1.0

# Icon corner radius as fraction of icon size (squircle)
ICON_CORNER_RADIUS_FACTOR = 0.22

# Running dot
INDICATOR_RADIUS = 2.5
INDICATOR_COLOR = (1.0, 1.0, 1.0, 0.95)

# Workspace badge
BADGE_FONT_SIZE = 9.0
BADGE_PADDING = 2
BADGE_RADIUS = 4.0
BADGE_BG = (0.0, 0.0, 0.0, 0.70)
BADGE_FG = (1.0, 1.0, 1.0, 1.0)

SEPARATOR_COLOR = (1.0, 1.0, 1.0, 0.25)


@dataclass
class DockItem:
    """Represents a single icon slot in the dock (pinned or running)."""

    app_id: str
    app_data: object
    is_pinned: bool = False
    is_trash: bool = False

    # Running state
    is_running: bool = False
    instance_address: Optional[str] = None
    app_class: Optional[str] = None
    client_data: Optional[dict] = None
    workspace_id: Optional[int] = None

    pixbuf: Optional[GdkPixbuf.Pixbuf] = None
    tooltip: str = ""

    # Animation state (mutated every frame by DockAnimator)
    current_scale: float = MIN_SCALE
    target_scale: float = MIN_SCALE

    # Set by DockLayout every frame; used by DockHitTest and draw code
    render_x: float = 0.0
    render_y: float = 0.0
    render_w: float = 0.0
    render_h: float = 0.0

    # Drag-and-drop readiness (for future use)
    drag_index: int = 0
    is_dragging: bool = False

    def hit(self, mx: float, my: float) -> bool:
        """Return True if (mx, my) falls within this item's render rectangle."""
        return (
            self.render_x <= mx <= self.render_x + self.render_w
            and self.render_y <= my <= self.render_y + self.render_h
        )


class DockModel:
    """Ordered list of DockItem objects for the dock."""

    def __init__(self):
        self.items: List[DockItem] = []

    def get_by_address(self, address: str) -> Optional[DockItem]:
        for item in self.items:
            if item.instance_address == address:
                return item
        return None

    def get_by_id(self, app_id: str) -> Optional[DockItem]:
        for item in self.items:
            if item.app_id.lower() == app_id.lower():
                return item
        return None

    def pinned_items(self) -> List[DockItem]:
        return [i for i in self.items if i.is_pinned]

    def running_only_items(self) -> List[DockItem]:
        return [i for i in self.items if not i.is_pinned and not i.is_trash]

    def has_running_only(self) -> bool:
        return any(not i.is_pinned and not i.is_trash for i in self.items)

    def has_pinned(self) -> bool:
        return any(i.is_pinned for i in self.items)


class DockLayout:
    """Computes gaussian target scales and push-apart render rects per frame."""

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
        # Estimate centres assuming uniform icon size (fast approximation)
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


class DockAnimator:
    """Drives the 60fps animation loop via GLib timeout."""

    def __init__(self, canvas: "DockCanvas"):
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

        w = canvas.get_allocated_width()
        h = canvas.get_allocated_height()
        DockLayout.compute(
            items,
            canvas._mouse_x,
            canvas._mouse_y,
            canvas._base_icon_size(),
            w if w > 1 else canvas._canvas_max_width(),
            h if h > 1 else canvas._canvas_height(),
            canvas._mouse_inside,
        )

        if dirty or canvas._needs_redraw:
            canvas._needs_redraw = False
            canvas.queue_draw()

        return self._running  # keep the timer alive


class DockHitTest:
    """Maps cursor coords to the DockItem under it via render rects."""

    @staticmethod
    def find_item(items: List[DockItem], mx: float, my: float) -> Optional[DockItem]:
        # Search in reverse so topmost (largest) icons take priority
        for item in reversed(items):
            if item.hit(mx, my):
                return item
        return None


class DockCanvas(Gtk.DrawingArea):
    """GTK drawing area with cairo rendering and full dock logic."""

    def __init__(self, parent_window: Window):
        super().__init__()

        self._parent = parent_window
        self.icon_resolver = IconResolver()
        self._hyprland_connection = modus_service._hyprland_connection

        self.model = DockModel()
        self._pixbuf_cache: Dict[Tuple[str, int], Optional[GdkPixbuf.Pixbuf]] = {}

        self._mouse_x: float = -9999.0
        self._mouse_y: float = -9999.0
        self._mouse_inside: bool = False
        self._needs_redraw: bool = True

        self._focused_address: str = ""
        self._dock_update_timer: Optional[int] = None
        self._hyprland_event_handlers: List = []

        self.pinned_apps: List = self._read_pinned_apps()
        self.menu = Gtk.Menu()
        self._configure_widget()
        self.animator = DockAnimator(self)

        self._rebuild_model()
        self.setup_app_monitoring()
        self.animator.start()

        self.show()

    # signal handlers + rgba visual
    def _configure_widget(self) -> None:
        # Allow mouse events
        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.LEAVE_NOTIFY_MASK
            | Gdk.EventMask.ENTER_NOTIFY_MASK
            | Gdk.EventMask.SCROLL_MASK
        )

        self.connect("draw", self._on_draw)
        self.connect("button-press-event", self._on_button_press)
        self.connect("motion-notify-event", self._on_motion)
        self.connect("enter-notify-event", self._on_enter)
        self.connect("leave-notify-event", self._on_leave)
        self.connect("size-allocate", self._on_size_allocate)

        self.set_hexpand(False)
        self.set_vexpand(False)
        self.set_app_paintable(True)

        screen = self.get_screen()
        if screen:
            visual = screen.get_rgba_visual()
            if visual:
                self.set_visual(visual)

    # icon size from config
    def _base_icon_size(self) -> int:
        return int(config().get("dock_icon_size", 52))

    # canvas height with room for magnification
    def _canvas_height(self) -> int:
        size = self._base_icon_size()
        return int(
            size * MAX_SCALE + CANVAS_TOP_PAD + 2 * BG_PADDING_V + INDICATOR_H + 4
        )

    # worst-case width for max zoom (window never resizes during animation)
    def _canvas_max_width(self) -> int:
        n = len(self.model.items)
        if n == 0:
            return 200
        size = self._base_icon_size()
        return int(
            n * size * MAX_SCALE + max(n - 1, 0) * ICON_GAP + 2 * BG_PADDING_H + 40
        )

    # same as max — pre-allocated so canvas stays fixed
    def _canvas_min_width(self) -> int:
        return self._canvas_max_width()

    # update gtk size request
    def _update_size_request(self) -> None:
        w = self._canvas_max_width()
        h = self._canvas_height()
        self.set_size_request(w, h)
        self.queue_resize()

    # mark dirty on resize
    def _on_size_allocate(self, widget, allocation) -> None:
        self._needs_redraw = True

    # gtk height-for-width geometry
    def do_get_preferred_height(self):
        h = self._canvas_height()
        return h, h

    # gtk width-for-height geometry
    def do_get_preferred_width(self):
        w = self._canvas_max_width()
        return w, w

    # lookup or cache pixbuf by icon name
    # lookup or cache pixbuf by icon name
    def _get_pixbuf(self, icon_name: str, size: int) -> Optional[GdkPixbuf.Pixbuf]:
        key = (icon_name, size)
        if key not in self._pixbuf_cache:
            self._pixbuf_cache[key] = self.icon_resolver.get_icon_pixbuf(
                icon_name, size
            )
        return self._pixbuf_cache[key]

    # clear pixbuf cache (e.g. on icon size change)
    def _clear_pixbuf_cache(self) -> None:
        self._pixbuf_cache.clear()

    # resolve icon from app data with fallback
    def _get_app_icon_pixbuf(
        self, app_data, app=None, size: Optional[int] = None
    ) -> Optional[GdkPixbuf.Pixbuf]:
        if size is None:
            size = self._base_icon_size()

        if app:
            try:
                pb = app.get_icon_pixbuf(size)
                if pb:
                    return pb
            except Exception:
                pass

        icon_name = ""
        if isinstance(app_data, dict):
            icon_name = app_data.get("window_class") or app_data.get("name") or ""
        elif isinstance(app_data, str):
            icon_name = app_data

        return self._get_pixbuf(icon_name or "application-x-executable", size)

    # rebuild dock items from pinned apps + running clients
    def _rebuild_model(self) -> None:
        old_scales: Dict[str, float] = {}
        for item in self.model.items:
            key = item.instance_address or item.app_id
            old_scales[key] = item.current_scale

        try:
            clients = self._get_clients()
            focused = self._get_focused_window()
            self._focused_address = (focused or {}).get("address", "")
        except Exception as e:
            logger.error(f"[DockCanvas] Error fetching clients: {e}")
            clients = []

        try:
            desktop_apps = get_desktop_applications(include_hidden=False)
        except Exception:
            desktop_apps = []

        new_items: List[DockItem] = []
        size = int(
            self._base_icon_size() * MAX_SCALE
        )  # load hi-res so magnified icons stay sharp

        running_classes_lower = {
            (c.get("class", "") or c.get("title", "")).lower()
            for c in clients
            if not c.get("hidden", False) and self._should_show_app_instance(c)
        }

        for app_data in self.pinned_apps:
            app_id = self._get_app_identifier(app_data)
            if not app_id:
                continue

            app = self._find_desktop_app(app_data, desktop_apps)
            pixbuf = self._get_app_icon_pixbuf(app_data, app, size)

            display_name = (
                app.display_name
                if app
                else (
                    app_data.get("display_name", app_id)
                    if isinstance(app_data, dict)
                    else app_id
                )
            )

            is_running = app_id.lower() in running_classes_lower

            item = DockItem(
                app_id=app_id,
                app_data=app_data,
                is_pinned=True,
                pixbuf=pixbuf,
                tooltip=display_name,
                is_running=is_running,
            )
            key = app_id
            item.current_scale = old_scales.get(key, MIN_SCALE)
            new_items.append(item)

        trash_has_files = self._trash_has_files()
        trash_svg = "trash-full.svg" if trash_has_files else "trash-empty.svg"
        try:
            svg_w = svg_file(f"misc/{trash_svg}")
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
            cr = cairo.Context(surface)
            rect = Rsvg.Rectangle()
            rect.x = rect.y = 0
            rect.width = size
            rect.height = size
            svg_w._handle.set_dpi(160)
            svg_w._handle.render_document(cr, rect)
            trash_pixbuf = Gdk.pixbuf_get_from_surface(surface, 0, 0, size, size)
            del svg_w
        except Exception:
            trash_pixbuf = self._get_pixbuf("user-trash", size)
        trash_item = DockItem(
            app_id="trash",
            app_data="trash",
            is_pinned=True,
            is_trash=True,
            pixbuf=trash_pixbuf,
            tooltip="Trash",
        )
        trash_item.current_scale = old_scales.get("trash", MIN_SCALE)
        new_items.append(trash_item)

        pinned_ids_lower = {
            self._get_app_identifier(a).lower() for a in self.pinned_apps
        }

        for client in clients:
            if client.get("hidden", False):
                continue
            if not self._should_show_app_instance(client):
                continue

            instance_address = client.get("address", "")
            app_class = client.get("class", "") or client.get("title", "")
            if not instance_address or not app_class:
                continue

            if app_class.lower() in pinned_ids_lower:
                # Update running state on the pinned item and store client data
                pinned = next(
                    (i for i in new_items if i.app_id.lower() == app_class.lower()),
                    None,
                )
                if pinned:
                    pinned.is_running = True
                    pinned.instance_address = instance_address
                    pinned.app_class = app_class
                    pinned.client_data = client
                    pinned.workspace_id = self._get_workspace_id(client)
                continue

            app = self._find_desktop_app(app_class, desktop_apps)
            pixbuf = self._get_app_icon_pixbuf(app_class, app, size)
            tooltip = client.get("title", app_class)
            if tooltip != app_class:
                tooltip = f"{app_class}: {tooltip}"

            item = DockItem(
                app_id=app_class,
                app_data=app_class,
                is_pinned=False,
                is_running=True,
                instance_address=instance_address,
                app_class=app_class,
                client_data=client,
                workspace_id=self._get_workspace_id(client),
                pixbuf=pixbuf,
                tooltip=tooltip,
            )
            key = instance_address
            item.current_scale = old_scales.get(key, MIN_SCALE)
            new_items.append(item)

        self.model.items = new_items
        self._needs_redraw = True

        DockLayout.compute(
            new_items,
            self._mouse_x,
            self._mouse_y,
            self._base_icon_size(),
            self._canvas_min_width(),
            self._canvas_height(),
            False,
        )

        self._update_size_request()

    # connect hyprland events for auto-rebuild
    def setup_app_monitoring(self) -> None:
        events = [
            "event::openwindow",
            "event::closewindow",
            "event::activewindow",
            "event::windowtitle",
            "event::movewindow",
            "event::workspace",
        ]
        for event in events:
            handler_id = self._hyprland_connection.connect(
                event, lambda *_: self.debounced_update_dock_apps()
            )
            self._hyprland_event_handlers.append(handler_id)

        GLib.idle_add(self._rebuild_model)

    # debounce rapid hyprland events (50ms window)
    def debounced_update_dock_apps(self) -> None:
        if self._dock_update_timer:
            GLib.source_remove(self._dock_update_timer)
        self._dock_update_timer = GLib.timeout_add(50, self._do_update)

    # actually run the rebuild
    def _do_update(self) -> bool:
        self._dock_update_timer = None
        try:
            self._rebuild_model()
        except Exception as e:
            logger.error(f"[DockCanvas] Error in update: {e}")
        return False

    # refresh icons and layout (e.g. config change)
    def update_icon_size(self) -> None:
        self._clear_pixbuf_cache()
        self._rebuild_model()

    # main cairo draw entry point
    def _on_draw(self, widget, cr: cairo.Context) -> bool:
        w = self.get_allocated_width()
        h = self.get_allocated_height()
        items = self.model.items
        base_size = self._base_icon_size()

        # Clear
        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        if not items:
            return True

        bg_x, bg_y, bg_w, bg_h = DockLayout.background_rect(items, base_size, w, h)

        self._draw_background(cr, bg_x, bg_y, bg_w, bg_h)

        if self.model.has_pinned() and self.model.has_running_only():
            self._draw_separator(cr, items, bg_y, bg_h, base_size)

        for item in items:
            self._draw_item(cr, item, base_size, h)

        return True

    # draw a rounded rectangle path
    def _rounded_rect(
        self,
        cr: cairo.Context,
        x: float,
        y: float,
        w: float,
        h: float,
        r: float,
    ) -> None:
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
        cr.close_path()

    # draw the frosted-glass pill background
    def _draw_background(
        self,
        cr: cairo.Context,
        x: float,
        y: float,
        w: float,
        h: float,
    ) -> None:
        r = min(BG_RADIUS, h / 2, w / 2)

        shadow_cx = x + w / 2
        shadow_cy = y + h + 4
        shadow_rx = w * 0.45
        shadow_ry = 5
        cr.save()
        cr.translate(shadow_cx, shadow_cy)
        cr.scale(shadow_rx, shadow_ry)
        pat = cairo.RadialGradient(0, 0, 0, 0, 0, 1)
        pat.add_color_stop_rgba(0.0, 0, 0, 0, 0.30)
        pat.add_color_stop_rgba(1.0, 0, 0, 0, 0.0)
        cr.set_source(pat)
        cr.arc(0, 0, 1, 0, 2 * math.pi)
        cr.fill()
        cr.restore()

        cr.save()
        self._rounded_rect(cr, x, y, w, h, r)
        cr.set_source_rgba(0.10, 0.10, 0.14, BG_ALPHA)
        cr.fill()
        cr.restore()

        cr.save()
        self._rounded_rect(cr, x, y, w, h, r)
        cr.clip()
        spec = cairo.LinearGradient(x, y, x, y + h * 0.55)
        spec.add_color_stop_rgba(0.00, 1.0, 1.0, 1.0, 0.22)  # bright edge
        spec.add_color_stop_rgba(0.30, 1.0, 1.0, 1.0, 0.08)
        spec.add_color_stop_rgba(1.00, 0.0, 0.0, 0.0, 0.08)  # slight darken at bottom
        cr.set_source(spec)
        cr.paint()
        cr.restore()

        cr.save()
        self._rounded_rect(cr, x + 0.5, y + 0.5, w - 1, h - 1, r)
        border_grad = cairo.LinearGradient(x, y, x, y + h)
        border_grad.add_color_stop_rgba(0.0, 1.0, 1.0, 1.0, BORDER_ALPHA)
        border_grad.add_color_stop_rgba(1.0, 1.0, 1.0, 1.0, BORDER_ALPHA * 0.4)
        cr.set_source(border_grad)
        cr.set_line_width(BORDER_WIDTH)
        cr.stroke()
        cr.restore()

    # vertical separator between pinned and running sections
    def _draw_separator(
        self,
        cr: cairo.Context,
        items: List[DockItem],
        bg_y: float,
        bg_h: float,
        base_size: int,
    ) -> None:
        last_pinned_x: Optional[float] = None
        first_running_x: Optional[float] = None

        for item in items:
            if item.is_pinned:
                last_pinned_x = item.render_x + item.render_w
            elif first_running_x is None:
                first_running_x = item.render_x

        if last_pinned_x is None or first_running_x is None:
            return

        sep_x = (last_pinned_x + first_running_x) / 2.0
        sep_margin = BG_PADDING_V + 4
        cr.save()
        cr.set_source_rgba(*SEPARATOR_COLOR)
        cr.set_line_width(SEPARATOR_WIDTH)
        cr.move_to(sep_x, bg_y + sep_margin)
        cr.line_to(sep_x, bg_y + bg_h - sep_margin)
        cr.stroke()
        cr.restore()

    # render a single dock icon + active dot + badge
    def _draw_item(
        self,
        cr: cairo.Context,
        item: DockItem,
        base_size: int,
        canvas_h: int,
    ) -> None:
        ix = item.render_x
        iy = item.render_y
        iw = item.render_w
        ih = item.render_h

        if iw <= 0 or ih <= 0:
            return

        if item.pixbuf:
            cr.save()
            # Scale the pixbuf to render size
            pb_w = item.pixbuf.get_width()
            pb_h = item.pixbuf.get_height()
            if pb_w > 0 and pb_h > 0:
                sx = iw / pb_w
                sy = ih / pb_h
                cr.translate(ix, iy)
                cr.scale(sx, sy)
                Gdk.cairo_set_source_pixbuf(cr, item.pixbuf, 0, 0)
                cr.paint()
            cr.restore()
        else:
            # Fallback: draw a coloured placeholder
            cr.save()
            cr.set_source_rgba(0.4, 0.4, 0.5, 0.8)
            cr.rectangle(ix, iy, iw, ih)
            cr.fill()
            cr.restore()

        if item.instance_address and item.instance_address == self._focused_address:
            dot_cx = ix + iw / 2.0
            dot_cy = iy + ih + 4
            cr.save()
            cr.set_source_rgba(*INDICATOR_COLOR)
            cr.arc(dot_cx, dot_cy, INDICATOR_RADIUS, 0, 2 * math.pi)
            cr.fill()
            cr.restore()

        if item.workspace_id is not None and not item.is_pinned:
            self._draw_workspace_badge(cr, ix, iy, iw, ih, str(item.workspace_id))

    # small badge showing the workspace number
    def _draw_workspace_badge(
        self,
        cr: cairo.Context,
        ix: float,
        iy: float,
        iw: float,
        ih: float,
        text: str,
    ) -> None:
        cr.save()
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(BADGE_FONT_SIZE)

        x_bearing, y_bearing, tw, th, _, _ = cr.text_extents(text)
        bw = tw + 2 * BADGE_PADDING
        bh = th + 2 * BADGE_PADDING

        bx = ix + iw - bw - 2
        by = iy + ih - bh - 2

        cr.set_source_rgba(*BADGE_BG)
        self._rounded_rect(cr, bx, by, bw, bh, BADGE_RADIUS)
        cr.fill()

        # Text
        cr.set_source_rgba(*BADGE_FG)
        cr.move_to(bx + BADGE_PADDING - x_bearing, by + BADGE_PADDING - y_bearing)
        cr.show_text(text)

        cr.restore()

    # track mouse position and update hover/tooltip
    def _on_motion(self, widget, event: Gdk.EventMotion) -> bool:
        self._mouse_x = event.x
        self._mouse_y = event.y

        items = self.model.items
        if items:
            size = self._base_icon_size()
            n = len(items)
            total_base = n * size + max(n - 1, 0) * ICON_GAP
            w = self.get_allocated_width()
            base_start_x = (w - total_base) / 2.0
            h = self.get_allocated_height()
            bg_h = size + 2 * BG_PADDING_V
            bg_y = h - INDICATOR_H - bg_h
            baseline_y = bg_y + BG_PADDING_V + size
            icon_top_y = baseline_y - size * MAX_SCALE
            self._mouse_inside = (
                base_start_x <= event.x <= base_start_x + total_base
                and icon_top_y <= event.y <= baseline_y
            )
        else:
            self._mouse_inside = False

        item = DockHitTest.find_item(self.model.items, event.x, event.y)
        self.set_tooltip_text(item.tooltip if item else "")

        if not self.animator._running:
            self.animator.start()

        return False

    # cursor enters dock canvas
    def _on_enter(self, widget, event: Gdk.EventCrossing) -> bool:
        self._mouse_inside = False
        self._parent.on_hover_enter()
        if not self.animator._running:
            self.animator.start()
        return False

    # cursor leaves dock canvas
    def _on_leave(self, widget, event: Gdk.EventCrossing) -> bool:
        self._mouse_inside = False
        self._mouse_x = -9999.0
        self._mouse_y = -9999.0
        self.set_tooltip_text("")
        self._parent.on_hover_leave()
        return False

    # handle click on dock items (launch, focus, menu)
    def _on_button_press(self, widget, event: Gdk.EventButton) -> bool:
        item = DockHitTest.find_item(self.model.items, event.x, event.y)
        if item is None:
            self._mouse_inside = False
            self._mouse_x = -9999.0
            self._mouse_y = -9999.0
            return False

        self._mouse_inside = False
        self._mouse_x = -9999.0
        self._mouse_y = -9999.0

        if item.is_trash:
            if event.button == 1:
                self._handle_trash_click()
            return True

        if item.is_pinned and not item.is_running:
            self._handle_pinned_click(event, item)
        elif item.is_running and not item.is_pinned:
            self._handle_instance_click(event, item)
        elif item.is_pinned and item.is_running:
            self._handle_instance_click(event, item)

        return True

    # launch/menu for pinned-only apps
    def _handle_pinned_click(self, event: Gdk.EventButton, item: DockItem) -> None:
        if event.button == 1:
            self._launch_app(item.app_data)
        elif event.button == 2:
            self._unpin_app(item.app_id)
        elif event.button == 3:
            self.show_menu(item.app_id)
            self.menu.popup_at_pointer(event)

    # focus window or launch for running instances
    def _handle_instance_click(self, event: Gdk.EventButton, item: DockItem) -> None:
        if event.button == 1:
            if item.instance_address:
                try:
                    GLib.spawn_command_line_async(
                        f"hyprctl dispatch 'hl.dsp.focus({{ window = "
                        f'"address:{item.instance_address}" }})\''
                    )
                except Exception as e:
                    logger.error(f"[DockCanvas] Error focusing window: {e}")
            else:
                self._launch_app(item.app_data)
        elif event.button == 2:
            if item.app_class and not self._is_app_pinned(item.app_class):
                self._pin_app(item.app_class)
        elif event.button == 3:
            app_id = item.app_class or item.app_id
            self.show_menu(app_id, instance_address=item.instance_address)
            self.menu.popup_at_pointer(event)

    # build and show the right-click context menu
    def show_menu(
        self,
        app_id: str,
        client=None,
        instance_address: Optional[str] = None,
    ) -> None:
        for child in self.menu.get_children():
            self.menu.remove(child)
            child.destroy()

        if instance_address:
            close_item = Gtk.MenuItem(label="Close")
            close_item.connect(
                "activate",
                lambda *_: self._close_running_app(instance_address),
            )
            self.menu.add(close_item)

            if app_id:
                self.menu.add(Gtk.SeparatorMenuItem())

        if app_id:
            is_pinned = self._is_app_pinned(app_id)
            pin_item = Gtk.MenuItem(label="Unpin" if is_pinned else "Pin")
            if is_pinned:
                pin_item.connect("activate", lambda *_: self._unpin_app(app_id))
            else:
                pin_item.connect("activate", lambda *_: self._pin_app(app_id))
            self.menu.add(pin_item)

        self.menu.show_all()

    # close a running window by hyprland address
    def _close_running_app(self, instance_address: str) -> None:
        try:
            self._hyprland_connection.send_command(
                f"dispatch closewindow address:{instance_address}"
            )
        except Exception as e:
            logger.error(f"[DockCanvas] Error closing window: {e}")

    # check if trash directory has files
    def _trash_has_files(self) -> bool:
        try:
            trash_path = os.path.expanduser("~/.local/share/Trash/files")
            return os.path.exists(trash_path) and len(os.listdir(trash_path)) > 0
        except Exception:
            return False

    # open trash in the default file manager
    def _handle_trash_click(self) -> None:
        try:
            trash_path = os.path.expanduser("~/.local/share/Trash/files")
            for fm in ["nautilus", "dolphin", "thunar", "nemo", "caja", "pcmanfm"]:
                try:
                    result = subprocess.run(
                        ["which", fm], capture_output=True, text=True
                    )
                    if result.returncode == 0:
                        subprocess.Popen([fm, trash_path])
                        return
                except Exception:
                    continue
        except Exception as e:
            logger.error(f"[DockCanvas] Error opening trash: {e}")

    # load pinned apps from dock.toml
    def _read_pinned_apps(self) -> list:
        try:
            if os.path.exists(PINNED_APPS_FILE):
                with open(PINNED_APPS_FILE, "r") as f:
                    data = tomlkit.load(f)
                    return list(data.get("pinned", []))
        except Exception as e:
            logger.error(f"[DockCanvas] Failed to read pinned apps: {e}")
        return []

    # save pinned apps to dock.toml
    def _write_pinned_apps(self) -> None:
        try:
            doc = tomlkit.document()
            arr = tomlkit.array()
            for app in self.pinned_apps:
                if isinstance(app, dict):
                    tbl = tomlkit.inline_table()
                    for k, v in app.items():
                        tbl[k] = v
                    arr.append(tbl)
                else:
                    arr.append(app)
            doc["pinned"] = arr
            with open(PINNED_APPS_FILE, "w") as f:
                tomlkit.dump(doc, f)
        except Exception as e:
            logger.error(f"[DockCanvas] Failed to write pinned apps: {e}")

    # add an app to the pinned list
    def _pin_app(self, app_class: str) -> bool:
        if self._is_app_pinned(app_class):
            return False
        try:
            desktop_apps = get_desktop_applications(include_hidden=False)
            app = self._find_desktop_app(app_class, desktop_apps)
            app_data = {
                "name": app.name if app else app_class,
                "display_name": (app.display_name or app.name) if app else app_class,
                "window_class": (getattr(app, "window_class", None) or app_class)
                if app
                else app_class,
                "executable": app.executable if app else app_class,
                "command_line": app.command_line if app else app_class,
            }
            self.pinned_apps.append(app_data)
        except Exception:
            self.pinned_apps.append(app_class)
        self._write_pinned_apps()
        self._rebuild_model()
        return True

    # remove an app from the pinned list
    def _unpin_app(self, app_identifier: str) -> bool:
        to_remove = [
            i
            for i, a in enumerate(self.pinned_apps)
            if self._matches_app_identifier(a, app_identifier)
        ]
        for i in reversed(to_remove):
            self.pinned_apps.pop(i)
        if to_remove:
            self._write_pinned_apps()
            self._rebuild_model()
            return True
        return False

    # check if an app is already pinned
    def _is_app_pinned(self, app_class: str) -> bool:
        return any(self._matches_app_identifier(a, app_class) for a in self.pinned_apps)

    # compare a pinned entry with an identifier
    def _matches_app_identifier(self, pinned_app, app_identifier: str) -> bool:
        if not app_identifier:
            return False
        if isinstance(pinned_app, dict):
            wc = pinned_app.get("window_class") or ""
            nm = pinned_app.get("name") or ""
            return (
                wc.lower() == app_identifier.lower()
                or nm.lower() == app_identifier.lower()
            )
        return (
            isinstance(pinned_app, str) and pinned_app.lower() == app_identifier.lower()
        )

    # extract identifier from app data
    def _get_app_identifier(self, app_data) -> str:
        if isinstance(app_data, dict):
            return app_data.get("name", "") or app_data.get("window_class", "")
        return str(app_data) if app_data else ""

    # launch an application via hyprctl
    def _launch_app(self, app_info) -> None:
        try:
            command_line = ""
            if hasattr(app_info, "command_line"):
                command_line = app_info.command_line
            elif isinstance(app_info, dict):
                command_line = app_info.get("command_line") or app_info.get(
                    "executable", ""
                )
            elif isinstance(app_info, str):
                command_line = app_info

            if not command_line:
                desktop_apps = get_desktop_applications(include_hidden=False)
                app = self._find_desktop_app(app_info, desktop_apps)
                if app:
                    command_line = app.command_line

            if command_line:
                cleaned = re.sub(r"%\w+", "", command_line).strip()
                final = f"hyprctl dispatch 'hl.dsp.exec_cmd([[uwsm app -- {cleaned}]])'"
                exec_shell_command_async(final)
            elif hasattr(app_info, "launch"):
                app_info.launch()
            else:
                logger.error(
                    f"[DockCanvas] Cannot determine launch command: {app_info}"
                )
        except Exception as e:
            logger.error(f"[DockCanvas] Failed to launch app: {e}")

    # find desktop app entry matching app_info
    def _find_desktop_app(self, app_info, desktop_apps):
        if not app_info:
            return None

        search_terms = []
        if isinstance(app_info, dict):
            search_terms = [
                app_info.get("window_class"),
                app_info.get("name"),
                app_info.get("executable"),
            ]
        else:
            search_terms = [app_info]

        search_terms = [s.lower() for s in search_terms if s and isinstance(s, str)]
        if not search_terms:
            return None

        expanded = list(search_terms)
        for term in search_terms:
            if "." in term:
                parts = term.split(".")
                if parts[-1] and parts[-1] not in expanded:
                    expanded.append(parts[-1])
            for sep in ["_", "-"]:
                if sep in term:
                    for part in term.split(sep):
                        if len(part) > 2 and part not in expanded:
                            expanded.append(part)

        # Priority 1: window_class exact
        for app in desktop_apps:
            ac = getattr(app, "window_class", None)
            if ac and ac.lower() in search_terms:
                return app

        # Priority 2: name/display_name exact
        for app in desktop_apps:
            names = [
                getattr(app, "name", None),
                getattr(app, "display_name", None),
            ]
            if any(n and n.lower() in expanded for n in names):
                return app

        # Priority 3: executable basename
        for app in desktop_apps:
            if app.executable:
                exe = os.path.basename(app.executable).lower()
                if exe in expanded:
                    common = ["kitty", "bash", "sh", "zsh", "python", "python3"]
                    if exe in common:
                        app_names = [
                            getattr(app, "name", ""),
                            getattr(app, "display_name", ""),
                        ]
                        if not any(exe in (n or "").lower() for n in app_names):
                            continue
                    return app

        # Priority 4: fuzzy containment
        for app in desktop_apps:
            at = [
                getattr(app, "name", ""),
                getattr(app, "display_name", ""),
                getattr(app, "window_class", ""),
            ]
            at = [t.lower() for t in at if t]
            for term in expanded:
                if len(term) < 3:
                    continue
                if any(term in t for t in at):
                    return app

        return None

    # fetch all hyprland windows
    def _get_clients(self) -> list:
        try:
            reply = self._hyprland_connection.send_command("j/clients").reply
            if not reply:
                return []
            return json.loads(reply.decode("utf-8"))
        except Exception as e:
            logger.error(f"[DockCanvas] Error getting clients: {e}")
            return []

    # fetch the currently focused window
    def _get_focused_window(self) -> Optional[dict]:
        try:
            reply = self._hyprland_connection.send_command("j/activewindow").reply
            if not reply:
                return None
            return json.loads(reply.decode("utf-8"))
        except Exception as e:
            logger.error(f"[DockCanvas] Error getting focused window: {e}")
            return None

    # extract workspace id from client data
    def _get_workspace_id(self, client: dict) -> Optional[int]:
        ws = client.get("workspace", {})
        if isinstance(ws, dict):
            return ws.get("id")
        elif isinstance(ws, (int, str)):
            try:
                return int(ws)
            except (ValueError, TypeError):
                return None
        return None

    # hide apps on special workspaces if configured
    def _should_show_app_instance(self, client: dict) -> bool:
        if not config().get("dock_hide_special_workspace_apps", True):
            return True
        ws_id = self._get_workspace_id(client)
        return False if ws_id is None else not is_special_workspace_id(ws_id)

    # clean up animator, timers, and hyprland handlers
    def destroy(self) -> None:
        self.animator.stop()

        if self._dock_update_timer:
            GLib.source_remove(self._dock_update_timer)
            self._dock_update_timer = None

        for handler_id in self._hyprland_event_handlers:
            try:
                self._hyprland_connection.disconnect(handler_id)
            except Exception:
                pass
        self._hyprland_event_handlers.clear()

        if self.menu:
            self.menu.destroy()

        super().destroy()


class Dock(Window):
    """Top-level wayland window that wraps DockCanvas with reveal + occlusion."""

    def __init__(self):
        super().__init__(
            layer="top",
            anchor="bottom center",
            exclusivity="none",
            title="modus-dock",
            name="dock",
        )

        screen = self.get_screen()
        if screen:
            visual = screen.get_rgba_visual()
            if visual:
                self.set_visual(visual)
        self.set_app_paintable(True)

        self.canvas = DockCanvas(self)

        from fabric.widgets.box import Box
        from fabric.widgets.eventbox import EventBox

        canvas_box = Box(
            name="dock-canvas-box",
            children=[self.canvas],
        )

        self.revealer = Revealer(
            child=canvas_box,
            transition_duration=200,
            transition_type="slide-up",
        )

        hover_strip = Box(
            name="dock-hover-strip",
        )

        outer_box = Box(
            name="dock-outer-box",
            orientation="v",
            children=[self.revealer, hover_strip],
        )

        self.children = EventBox(
            events=["enter-notify", "leave-notify"],
            child=outer_box,
            on_enter_notify_event=lambda *_: self.on_hover_enter(),
            on_leave_notify_event=lambda *_: self.on_hover_leave(),
        )

        self.dock_height = 100
        self.is_hovered = False
        self.hide_ticket = 0
        self._startup_grace = True  # block occlusion hiding for first 2s

        self.revealer.set_reveal_child(True)
        self.show_all()

        on_config_change(self._on_config_change)

        if config().get("dock_auto_hide", True):
            GLib.timeout_add(2000, self._start_occlusion_monitoring)
        else:
            self._occlusion_timer_id = None

    # start occlusion checks after startup grace period
    def _start_occlusion_monitoring(self) -> bool:
        self._startup_grace = False
        self.setup_occlusion_monitoring()
        return False  # one-shot timer

    # respond to config changes (visibility, icon size, auto-hide)
    def _on_config_change(self, new_config, old_config) -> None:
        if config().has_changed("dock_enabled", old_config):
            self._update_visibility()

        if config().has_changed("dock_icon_size", old_config):
            self.canvas.update_icon_size()

        if config().has_changed("dock_auto_hide", old_config):
            if new_config.get("dock_auto_hide", True):
                self.setup_occlusion_monitoring()
            else:
                if hasattr(self, "_occlusion_timer_id") and self._occlusion_timer_id:
                    GLib.source_remove(self._occlusion_timer_id)
                    self._occlusion_timer_id = None
                self.revealer.set_reveal_child(True)

        if config().has_changed("dock_hide_special_workspace_apps", old_config):
            self.canvas._rebuild_model()

    # show/hide dock based on config
    def _update_visibility(self) -> None:
        if config().get("dock_enabled", True):
            self.show()
            self.revealer.set_reveal_child(True)
        else:
            self.hide()

    # show dock when cursor enters its area
    def on_hover_enter(self) -> None:
        self.is_hovered = True
        self.hide_ticket = random.getrandbits(32)
        self.revealer.set_reveal_child(True)

    # hide dock after delay if occluded
    def on_hover_leave(self) -> None:
        self.is_hovered = False
        ticket = random.getrandbits(32)
        self.hide_ticket = ticket

        def delayed_hide(t):
            if t == self.hide_ticket and not self.is_hovered:
                if config().get("dock_auto_hide", True):
                    is_occ = config().get(
                        "dock_always_occluded", False
                    ) or check_occlusion(("bottom", self.dock_height))
                    if is_occ:
                        self.revealer.set_reveal_child(False)
            return False

        GLib.timeout_add(500, delayed_hide, ticket)

    # periodic check for windows overlapping the dock
    def setup_occlusion_monitoring(self) -> None:
        if hasattr(self, "_occlusion_timer_id") and self._occlusion_timer_id:
            GLib.source_remove(self._occlusion_timer_id)
            self._occlusion_timer_id = None

        def check_dock_occlusion() -> bool:
            try:
                if config().get("dock_always_occluded", False):
                    is_occ = True
                else:
                    is_occ = check_occlusion(("bottom", self.dock_height))

                if is_occ and not self.is_hovered and self.revealer.get_reveal_child():
                    self.revealer.set_reveal_child(False)
                elif not is_occ and not self.revealer.get_reveal_child():
                    self.revealer.set_reveal_child(True)
                elif is_occ and self.is_hovered:
                    if not self.revealer.get_reveal_child():
                        self.revealer.set_reveal_child(True)
            except Exception as e:
                logger.error(f"[Dock] Occlusion check error: {e}")
            return True

        self._occlusion_timer_id = GLib.timeout_add(300, check_dock_occlusion)

    # clean up timers and canvas
    def destroy(self) -> None:
        if hasattr(self, "_occlusion_timer_id") and self._occlusion_timer_id:
            GLib.source_remove(self._occlusion_timer_id)
            self._occlusion_timer_id = None

        if hasattr(self, "canvas") and self.canvas:
            self.canvas.destroy()

        super().destroy()
