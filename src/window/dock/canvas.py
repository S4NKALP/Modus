import math
from typing import Dict, List, Optional, Tuple

import cairo
import tomlkit
from fabric.utils import (
    Gdk,
    GdkPixbuf,
    GLib,
    Gtk,
    get_desktop_applications,
    logger,
    os,
)
from gi.repository import Rsvg

from services.config import config
from services.modus import (
    close_window,
    get_active_window,
    get_clients,
    get_modus_service,
    launch_app,
    open_trash,
)
from utils.functions import clear_children, is_special_workspace_id
from utils.gtk_utils import svg_file
from utils.icon_resolver import IconResolver

from .animator import DockAnimator
from .constants import (
    BADGE_BG,
    BADGE_FG,
    BADGE_FONT_SIZE,
    BADGE_PADDING,
    BADGE_RADIUS,
    BG_PADDING_H,
    BG_PADDING_V,
    CANVAS_TOP_PAD,
    ICON_GAP,
    INDICATOR_COLOR,
    INDICATOR_H,
    INDICATOR_RADIUS,
    MAX_SCALE,
    MIN_SCALE,
    PINNED_APPS_FILE,
    SEPARATOR_COLOR,
    SEPARATOR_WIDTH,
)
from .items import DockHitTest, DockItem, DockModel
from .layout import DockLayout

_PIXBUF_CACHE_MAX = 64

# Terminal/interpreter executables whose name alone should not force a match
# against unrelated desktop apps during dock item resolution.
_COMMON_EXECUTABLES = ("kitty", "bash", "sh", "zsh", "python", "python3")


class DockCanvas(Gtk.DrawingArea):
    def __init__(self, parent_window):
        super().__init__()

        self._parent = parent_window
        self.icon_resolver = IconResolver()
        self._hyprland_connection = get_modus_service()._hyprland_connection

        self.model = DockModel()
        self._pixbuf_cache: Dict[Tuple[str, int], Optional[GdkPixbuf.Pixbuf]] = {}

        self._mouse_x: float = -9999.0
        self._mouse_y: float = -9999.0
        self._mouse_inside: bool = False
        self._needs_redraw: bool = True

        self._focused_address: str = ""
        self._dock_update_timer: Optional[int] = None
        self._hyprland_event_handlers: List = []
        self._last_requested_width: int = 0
        self._last_requested_height: int = 0
        self._modus_ws_handler: int | None = None

        self._desktop_apps: list = []
        self._trash_pixbuf: Optional[GdkPixbuf.Pixbuf] = None
        self._cached_trash_full: Optional[bool] = None
        self._cached_trash_size: int = 0

        self.pinned_apps: List = self._read_pinned_apps()
        self.menu = Gtk.Menu()
        self._configure_widget()
        self.animator = DockAnimator(self)

        self._rebuild_model()
        self.setup_app_monitoring()
        self.animator.start()

        self.show()

    def _configure_widget(self) -> None:
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

    def _base_icon_size(self) -> int:
        return int(config().get("dock_icon_size", 52))

    def _icon_cache_size(self) -> int:
        return int(self._base_icon_size() * MAX_SCALE)

    def _get_desktop_apps(self) -> list:
        if not self._desktop_apps:
            try:
                self._desktop_apps = get_desktop_applications(include_hidden=False)
            except Exception as e:
                logger.warning(f"[dock] Failed to load desktop applications: {e}")
                self._desktop_apps = []
        return self._desktop_apps

    def _canvas_height(self) -> int:
        size = self._base_icon_size()
        return int(
            size * MAX_SCALE + CANVAS_TOP_PAD + 2 * BG_PADDING_V + INDICATOR_H + 4
        )

    def _canvas_max_width(self) -> int:
        n = len(self.model.items)
        if n == 0:
            return 200
        size = self._base_icon_size()
        return int(
            n * size * MAX_SCALE + max(n - 1, 0) * ICON_GAP + 2 * BG_PADDING_H + 40
        )

    def _canvas_min_width(self) -> int:
        return self._canvas_max_width()

    def _update_size_request(self) -> None:
        w = self._canvas_max_width()
        h = self._canvas_height()
        self.set_size_request(w, h)
        self.queue_resize()

    def _on_size_allocate(self, widget, allocation) -> None:
        self._needs_redraw = True

    def do_get_preferred_height(self):
        h = self._canvas_height()
        return h, h

    def do_get_preferred_width(self):
        w = self._canvas_max_width()
        return w, w

    def _get_pixbuf(self, icon_name: str, size: int) -> Optional[GdkPixbuf.Pixbuf]:
        key = (icon_name, size)
        if key not in self._pixbuf_cache:
            while len(self._pixbuf_cache) >= _PIXBUF_CACHE_MAX:
                self._pixbuf_cache.pop(next(iter(self._pixbuf_cache)), None)
            self._pixbuf_cache[key] = self.icon_resolver.get_icon_pixbuf(
                icon_name, size
            )
        return self._pixbuf_cache[key]

    def _clear_pixbuf_cache(self) -> None:
        self._pixbuf_cache.clear()

    def _get_app_icon_pixbuf(
        self, app_data, app=None, size: Optional[int] = None
    ) -> Optional[GdkPixbuf.Pixbuf]:
        if size is None:
            size = self._base_icon_size()

        icon_name = None
        if app and hasattr(app, "icon_name") and app.icon_name:
            icon_name = app.icon_name
        elif isinstance(app_data, dict):
            icon_name = app_data.get("window_class") or app_data.get("name") or ""
        elif isinstance(app_data, str):
            icon_name = app_data

        return self._get_pixbuf(icon_name or "application-x-executable", size)

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

        desktop_apps = self._get_desktop_apps()
        size = self._icon_cache_size()

        active_clients = {
            c.get("address"): c
            for c in clients
            if not c.get("hidden", False) and self._should_show_app_instance(c)
        }

        running_classes_lower = {
            (c.get("class", "") or c.get("title", "")).lower()
            for c in active_clients.values()
        }

        pinned_ids_lower = {
            self._get_app_identifier(a).lower() for a in self.pinned_apps
        }

        new_items: List[DockItem] = []

        for app_data in self.pinned_apps:
            app_id = self._get_app_identifier(app_data)
            if not app_id:
                continue

            existing = self.model.get_by_id(app_id)
            if existing and existing.is_pinned:
                item = existing
                currently_running = app_id.lower() in running_classes_lower
                item.is_running = currently_running
                if not currently_running:
                    item.instance_address = None
                    item.client_data = None
            else:
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
                item = DockItem(
                    app_id=app_id,
                    app_data=app_data,
                    is_pinned=True,
                    pixbuf=pixbuf,
                    tooltip=display_name,
                )

            key = app_id
            item.current_scale = old_scales.get(key, MIN_SCALE)
            new_items.append(item)

        self._update_trash_item(new_items, old_scales, size)

        for client in active_clients.values():
            instance_address = client.get("address", "")
            app_class = client.get("class", "") or client.get("title", "")
            if not instance_address or not app_class:
                continue

            if app_class.lower() in pinned_ids_lower:
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

            existing = self.model.get_by_address(instance_address)
            if existing and not existing.is_pinned and not existing.is_trash:
                item = existing
                tooltip = client.get("title", app_class)
                item.tooltip = (
                    f"{app_class}: {tooltip}" if tooltip != app_class else app_class
                )
                item.client_data = client
                item.workspace_id = self._get_workspace_id(client)
            else:
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

    def _update_trash_item(
        self,
        new_items: List[DockItem],
        old_scales: Dict[str, float],
        size: int,
    ) -> None:
        trash_full = self._trash_has_files()
        if (
            self._trash_pixbuf is None
            or trash_full != self._cached_trash_full
            or size != self._cached_trash_size
        ):
            self._cached_trash_full = trash_full
            self._cached_trash_size = size
            trash_svg = "trash-full.svg" if trash_full else "trash-empty.svg"
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
                self._trash_pixbuf = Gdk.pixbuf_get_from_surface(
                    surface, 0, 0, size, size
                )
            except Exception as e:
                logger.warning(f"[canvas] Failed to render trash SVG: {e}")
                self._trash_pixbuf = self._get_pixbuf("user-trash", size)

        existing = self.model.get_by_id("trash")
        if existing and existing.is_trash:
            item = existing
            item.pixbuf = self._trash_pixbuf
        else:
            item = DockItem(
                app_id="trash",
                app_data="trash",
                is_pinned=True,
                is_trash=True,
                pixbuf=self._trash_pixbuf,
                tooltip="Trash",
            )
        item.current_scale = old_scales.get("trash", MIN_SCALE)
        new_items.append(item)

    def setup_app_monitoring(self) -> None:
        events = [
            "event::openwindow",
            "event::closewindow",
            "event::movewindow",
        ]
        for event in events:
            handler_id = self._hyprland_connection.connect(
                event, lambda *_: self.debounced_update_dock_apps()
            )
            self._hyprland_event_handlers.append(handler_id)

        self._hyprland_event_handlers.append(
            self._hyprland_connection.connect(
                "event::activewindow", self._on_active_window_changed
            )
        )

        self._hyprland_event_handlers.append(
            self._hyprland_connection.connect(
                "event::windowtitle", self._on_window_title_changed
            )
        )

        self._modus_ws_handler = get_modus_service().connect(
            "current-workspace-changed", self._on_modus_workspace_changed
        )

        GLib.idle_add(self._rebuild_model)

    def _on_modus_workspace_changed(self, service, value) -> None:
        try:
            clients = self._get_clients()
        except Exception as e:
            logger.warning(f"[canvas] clients = self._get_clients() failed: {e}")
            return
        client_map = {c.get("address"): c for c in clients if c.get("address")}
        for item in self.model.items:
            if item.instance_address and item.instance_address in client_map:
                item.workspace_id = self._get_workspace_id(
                    client_map[item.instance_address]
                )
        self._needs_redraw = True
        self.queue_draw()

    def _on_active_window_changed(self, *args) -> None:
        try:
            focused = get_active_window()
            self._focused_address = (focused or {}).get("address", "")
        except Exception:
            self._focused_address = ""
        self._needs_redraw = True
        self.queue_draw()

    def _on_window_title_changed(self, _hyprland, signal) -> None:
        try:
            address = signal.data[0]
            if not address:
                return
            # Fetch client data BEFORE iterating so the expensive IPC call
            # doesn't hold a stale reference to model items across rebuilds.
            clients = self._get_clients()
            client = next((c for c in clients if c.get("address") == address), None)
            if not client:
                return
            title = client.get("title", "")
            # Re-verify the item still exists in the CURRENT model — a
            # debounced rebuild may have replaced the list since the signal.
            for item in self.model.items:
                if item.instance_address == address:
                    app_class = item.app_class or ""
                    item.tooltip = (
                        f"{app_class}: {title}" if title != app_class else app_class
                    )
                    break
        except Exception as e:
            logger.warning(f"[canvas] address = signal.data[0] failed: {e}")
        self._needs_redraw = True
        self.queue_draw()

    def debounced_update_dock_apps(self) -> None:
        if self._dock_update_timer:
            GLib.source_remove(self._dock_update_timer)
        self._dock_update_timer = GLib.timeout_add(50, self._do_update)

    def _do_update(self) -> bool:
        self._dock_update_timer = None
        try:
            self._rebuild_model()
        except Exception as e:
            logger.error(f"[DockCanvas] Error in update: {e}")
        return False

    def update_icon_size(self) -> None:
        self._clear_pixbuf_cache()
        self._rebuild_model()

    def _on_draw(self, widget, cr: cairo.Context) -> bool:
        w = self.get_allocated_width()
        h = self.get_allocated_height()
        items = self.model.items
        base_size = self._base_icon_size()

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

    def _draw_background(
        self,
        cr: cairo.Context,
        x: float,
        y: float,
        w: float,
        h: float,
    ) -> None:
        context = self.get_style_context()
        context.save()
        context.add_class("dock-background")

        # Render the CSS background (includes background-color, background-image/gradients, box-shadow)
        Gtk.render_background(context, cr, x, y, w, h)

        # Render the CSS border (includes border-color, border-width, border-style)
        Gtk.render_frame(context, cr, x, y, w, h)

        context.restore()

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

        cr.set_source_rgba(*BADGE_FG)
        cr.move_to(bx + BADGE_PADDING - x_bearing, by + BADGE_PADDING - y_bearing)
        cr.show_text(text)

        cr.restore()

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

    def _on_enter(self, widget, event: Gdk.EventCrossing) -> bool:
        self._mouse_inside = False
        self._parent.on_hover_enter()
        if not self.animator._running:
            self.animator.start()
        return False

    def _on_leave(self, widget, event: Gdk.EventCrossing) -> bool:
        self._mouse_inside = False
        self._mouse_x = -9999.0
        self._mouse_y = -9999.0
        self.set_tooltip_text("")
        self._parent.on_hover_leave()
        return False

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
        elif (item.is_running and not item.is_pinned) or (
            item.is_pinned and item.is_running
        ):
            self._handle_instance_click(event, item)

        return True

    def _handle_pinned_click(self, event: Gdk.EventButton, item: DockItem) -> None:
        if event.button == 1:
            self._launch_app(item.app_data)
        elif event.button == 2:
            self._unpin_app(item.app_id)
        elif event.button == 3:
            self.show_menu(item.app_id)
            self.menu.popup_at_pointer(event)

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

    def show_menu(
        self,
        app_id: str,
        client=None,
        instance_address: Optional[str] = None,
    ) -> None:
        clear_children(self.menu)

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

    def _close_running_app(self, instance_address: str) -> None:
        close_window(instance_address)

    def _trash_has_files(self) -> bool:
        try:
            trash_path = os.path.expanduser("~/.local/share/Trash/files")
            return os.path.exists(trash_path) and len(os.listdir(trash_path)) > 0
        except Exception as e:
            logger.warning(
                f"[canvas] trash_path = os.path.expanduser('~/.local/share/Trash/fil... failed: {e}"
            )
            return False

    def _handle_trash_click(self) -> None:
        open_trash()

    def _read_pinned_apps(self) -> list:
        try:
            if os.path.exists(PINNED_APPS_FILE):
                with open(PINNED_APPS_FILE) as f:
                    data = tomlkit.load(f)
                    return list(data.get("pinned", []))
        except Exception as e:
            logger.error(f"[DockCanvas] Failed to read pinned apps: {e}")
        return []

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

    def _pin_app(self, app_class: str) -> bool:
        if self._is_app_pinned(app_class):
            return False
        try:
            app = self._find_desktop_app(app_class, self._get_desktop_apps())
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
        except Exception as e:
            logger.warning(
                f"[canvas] app = self._find_desktop_app(app_class, self._get_desktop... failed: {e}"
            )
            self.pinned_apps.append(app_class)
        self._write_pinned_apps()
        self._rebuild_model()
        return True

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

    def _is_app_pinned(self, app_class: str) -> bool:
        return any(self._matches_app_identifier(a, app_class) for a in self.pinned_apps)

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

    def _get_app_identifier(self, app_data) -> str:
        if isinstance(app_data, dict):
            return app_data.get("name", "") or app_data.get("window_class", "")
        return str(app_data) if app_data else ""

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
                app = self._find_desktop_app(app_info, self._get_desktop_apps())
                if app:
                    command_line = app.command_line

            if command_line:
                launch_app(command_line)
            elif hasattr(app_info, "launch"):
                from window.globalmenu.launch import launch_desktop_app

                launch_desktop_app(app_info)
            else:
                logger.error(
                    f"[DockCanvas] Cannot determine launch command: {app_info}"
                )
        except Exception as e:
            logger.error(f"[DockCanvas] Failed to launch app: {e}")

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

        # Check exact desktop file name first
        for app in desktop_apps:
            app_id = getattr(app, "id", None)
            if not app_id and hasattr(app, "get_id"):
                app_id = app.get_id()
            if app_id:
                app_id_clean = app_id.lower().replace(".desktop", "")
                if app_id_clean in search_terms:
                    return app

        for app in desktop_apps:
            ac = getattr(app, "window_class", None)
            if ac and ac.lower() in search_terms:
                return app

        for app in desktop_apps:
            names = [
                getattr(app, "name", None),
                getattr(app, "display_name", None),
            ]
            if any(n and n.lower() in expanded for n in names):
                return app

        for app in desktop_apps:
            if app.executable:
                exe = os.path.basename(app.executable).lower()
                if exe in expanded:
                    if exe in _COMMON_EXECUTABLES:
                        app_names = [
                            getattr(app, "name", ""),
                            getattr(app, "display_name", ""),
                        ]
                        if not any(exe in (n or "").lower() for n in app_names):
                            continue
                    return app

        best_match = None
        best_score = -1

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
                for t in at:
                    if term == t:
                        return app
                    if term in t:
                        score = 0
                        if t.startswith(term):
                            score += 2
                        if f" {term} " in f" {t} ":
                            score += 2
                        score += len(term) / max(len(t), 1)
                        if score > best_score:
                            best_score = score
                            best_match = app

        return best_match

    def _get_clients(self) -> list:
        return get_clients()

    def _get_focused_window(self) -> Optional[dict]:
        return get_active_window()

    def _get_workspace_id(self, client: dict) -> Optional[int]:
        ws = client.get("workspace", {})
        if isinstance(ws, dict):
            return ws.get("id")
        elif isinstance(ws, (int, str)):
            try:
                return int(ws)
            except (ValueError, TypeError) as e:
                logger.warning(f"[canvas] return int(ws) failed: {e}")
                return None
        return None

    def _should_show_app_instance(self, client: dict) -> bool:
        if not config().get("dock_hide_special_workspace_apps", True):
            return True
        ws_id = self._get_workspace_id(client)
        return False if ws_id is None else not is_special_workspace_id(ws_id)

    def destroy(self) -> None:
        self.animator.stop()

        if self._dock_update_timer:
            GLib.source_remove(self._dock_update_timer)
            self._dock_update_timer = None

        for handler_id in self._hyprland_event_handlers:
            try:
                self._hyprland_connection.disconnect(handler_id)
            except Exception as e:
                logger.warning(
                    f"[canvas] self._hyprland_connection.disconnect(handler_id) failed: {e}"
                )
        self._hyprland_event_handlers.clear()

        if self._modus_ws_handler is not None:
            try:
                get_modus_service().disconnect(self._modus_ws_handler)
            except Exception as e:
                logger.warning(
                    f"[canvas] get_modus_service().disconnect(self._modus_ws_handler) failed: {e}"
                )
            self._modus_ws_handler = None

        if self.menu:
            self.menu.destroy()

        super().destroy()
