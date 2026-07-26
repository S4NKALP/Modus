import importlib
import os
import pkgutil

import tomlkit
from fabric.utils import Gdk, GLib, Gtk, logger
from fabric.widgets.box import Box
from fabric.widgets.wayland import WaylandWindow

from shared.widgets.animator import Animator
from utils.gtk_utils import toml_file
from window.desktop.registry import DesktopWidgetRegistry

# Dynamically import all modules in this package to register widgets
_dir = os.path.dirname(__file__)
for _, _name, _ in pkgutil.iter_modules([_dir]):
    if _name not in ("main", "registry", "widgets"):
        try:
            importlib.import_module(f".{_name}", package=__package__)
        except Exception as e:
            logger.error(f"Failed to load desktop widget module {_name}: {e}")

#  Config-backed position manager (stores percentage-based positions)          #

_DEFAULT_POSITIONS = [
    {"key": "date", "px": 0.0, "py": 0.0},
    {"key": "weather", "px": 0.0974, "py": 0.0},
    {"key": "calendar", "px": 0.19271, "py": 0.0},
    {"key": "cpu_info", "px": 0.81042, "py": 0.82732},
    {"key": "ram_info", "px": 0.90521, "py": 0.82732},
]


class PositionManager:
    """Manages widget positions stored in desktop.toml as fractional coords."""

    _file = toml_file("desktop.toml")

    @classmethod
    def _read(cls):
        try:
            if os.path.exists(cls._file):
                with open(cls._file) as f:
                    return tomlkit.load(f)
        except Exception as e:
            logger.error(f"Failed to read desktop.toml: {e}")
        return {}

    @classmethod
    def _write(cls, data):
        try:
            os.makedirs(os.path.dirname(cls._file), exist_ok=True)
            with open(cls._file, "w") as f:
                tomlkit.dump(data, f)
        except Exception as e:
            logger.error(f"Failed to write desktop.toml: {e}")

    @classmethod
    def get_widgets(cls, monitor_id: int) -> list[dict]:
        state = cls._read()
        mid_str = str(monitor_id)
        if mid_str not in state:
            state[mid_str] = list(_DEFAULT_POSITIONS)
            cls._write(state)
        return state[mid_str]

    @classmethod
    def save_position(cls, monitor_id: int, key: str, px: float, py: float) -> None:
        state = cls._read()
        mid_str = str(monitor_id)
        if mid_str not in state:
            state[mid_str] = list(_DEFAULT_POSITIONS)
        for entry in state[mid_str]:
            if entry["key"] == key:
                entry["px"] = round(max(0.0, min(1.0, px)), 5)
                entry["py"] = round(max(0.0, min(1.0, py)), 5)
                break
        else:
            state[mid_str].append({"key": key, "px": px, "py": py})
        cls._write(state)

    @classmethod
    def remove(cls, monitor_id: int, key: str) -> bool:
        state = cls._read()
        mid_str = str(monitor_id)
        if mid_str not in state:
            return False
        before = len(state[mid_str])
        state[mid_str] = [e for e in state[mid_str] if e["key"] != key]
        cls._write(state)
        return len(state[mid_str]) < before


position_manager = PositionManager()


class DesktopWidgetWindow(WaylandWindow):
    def __init__(self, monitor_id: int) -> None:
        self._monitor_id = monitor_id
        self._fixed = Gtk.Fixed()
        self._children: dict[str, Gtk.EventBox] = {}
        self._win_w = 1
        self._win_h = 1
        self._old_w = 0
        self._old_h = 0
        self._recalc_in_progress = False
        self._recalc_timer: int | None = None
        self._ready = False
        self._in_size_allocate = False
        self._edit_mode = False

        # Drag state
        self._dragging_key: str | None = None
        self._drag_start_wx: int = 0
        self._drag_start_wy: int = 0
        self._drag_start_px: int = 0
        self._drag_start_py: int = 0

        self._root = Box(h_expand=True, v_expand=True)

        self._overlay = Gtk.Overlay()
        self._overlay.add(self._fixed)

        self._root.add(self._overlay)

        # Get initial dimensions from monitor so we don't spawn at 0,0
        monitor = Gdk.Display.get_default().get_monitor(monitor_id)
        if monitor:
            geom = monitor.get_geometry()
            self._win_w = max(1, geom.width)
            self._win_h = max(1, geom.height)

        # Fade animators
        self._fade_animator = Animator(
            bezier_curve=(0.4, 0.0, 0.2, 1.0),
            duration=0.2,
            min_value=0.0,
            max_value=1.0,
            tick_widget=self._root,
        )
        self._fade_animator.connect("notify::value", self._on_fade_value)
        self._fade_animator.connect("finished", self._on_fade_finished)

        self._fade_out_animator = Animator(
            bezier_curve=(0.4, 0.0, 0.2, 1.0),
            duration=0.2,
            min_value=0.0,
            max_value=1.0,
            tick_widget=self._root,
        )
        self._fade_out_animator.connect("notify::value", self._on_fade_out_value)
        self._fade_out_animator.connect("finished", self._on_fade_out_finished)
        self._fixed.set_opacity(0.0)

        super().__init__(
            monitor=monitor_id,
            anchor="left right top bottom",
            exclusivity="ignore",
            layer="background",
            child=self._root,
            visible=True,
            name=f"desktop-widgets-{monitor_id}",
        )

        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )
        self.connect("size-allocate", self._on_size_allocate)
        self.connect("button-press-event", self._on_window_button_press)
        self.connect("button-release-event", self._on_window_button_release)
        self.connect("motion-notify-event", self._on_window_motion)

        GLib.timeout_add(50, self._initial_build)

    # lifecycle
    def _initial_build(self) -> bool:
        self._ready = True
        alloc = self.get_allocation()
        if alloc.width > 1:
            self._win_w = alloc.width
            self._win_h = alloc.height
        self.rebuild()
        self._fade_in()
        return False

    # fade
    def _on_fade_value(self, animator, _) -> None:
        self._fixed.set_opacity(animator.value)

    def _on_fade_finished(self, animator) -> None:
        self._fixed.set_opacity(1.0)

    def _fade_in(self) -> None:
        if self._fade_animator.playing:
            return
        self._fade_out_animator.pause()
        self._fade_animator.value = self._fixed.get_opacity()
        self._fade_animator.min_value = self._fixed.get_opacity()
        self._fade_animator.max_value = 1.0
        self._fade_animator.play()

    def _fade_out(self) -> None:
        self._fade_animator.pause()
        self._fade_out_animator.min_value = 0.0
        self._fade_out_animator.max_value = self._fixed.get_opacity()
        self._fade_out_animator.value = self._fixed.get_opacity()
        self._fade_out_animator.play()

    def _on_fade_out_value(self, animator, _) -> None:
        self._fixed.set_opacity(animator.value)

    def _on_fade_out_finished(self, animator) -> None:
        self._fixed.set_opacity(0.0)

    # right-click context menu (window level — edit mode toggle only)
    def _on_window_button_press(self, widget, event: Gdk.EventButton) -> bool:
        if event.button == 3:
            menu = Gtk.Menu()
            label_text = "Done Edit" if self._edit_mode else "Edit Widgets"
            edit_item = Gtk.CheckMenuItem(label=label_text)
            edit_item.set_active(self._edit_mode)
            edit_item.connect("toggled", self._on_edit_toggled)
            menu.append(edit_item)
            menu.show_all()
            menu.popup_at_pointer(event)
            return True

        if event.button == 1 and self._edit_mode:
            # Find which widget was clicked via hit test
            key = self._hit_test(int(event.x_root), int(event.y_root))
            if key is None:
                return False
            eb = self._children[key]
            if eb.get_window():
                eb.get_window().raise_()
            alloc = eb.get_allocation()
            self._dragging_key = key
            self._drag_start_wx = alloc.x
            self._drag_start_wy = alloc.y
            self._drag_start_px = int(event.x_root)
            self._drag_start_py = int(event.y_root)
            eb.set_opacity(0.5)
            self._set_cursor(eb, "grabbing")
            return True

        return False

    def _on_window_button_release(self, _widget, event: Gdk.EventButton) -> bool:
        if self._dragging_key is not None and event.button == 1:
            eb = self._children.get(self._dragging_key)
            if eb is not None:
                self._finish_drag(eb, self._dragging_key)
            else:
                self._dragging_key = None
            return True
        return False

    def _on_window_motion(self, _widget, event: Gdk.EventMotion) -> bool:
        if self._dragging_key is None:
            return False

        key = self._dragging_key
        eb = self._children.get(key)
        if eb is None:
            self._dragging_key = None
            return False

        dx = int(event.x_root) - self._drag_start_px
        dy = int(event.y_root) - self._drag_start_py

        aw = eb.get_allocation().width
        ah = eb.get_allocation().height
        new_x = max(0, min(self._win_w - aw, self._drag_start_wx + dx))
        new_y = max(0, min(self._win_h - ah, self._drag_start_wy + dy))

        self._fixed.move(eb, new_x, new_y)
        eb._target_x = new_x
        eb._target_y = new_y

        return True

    def _hit_test(self, rx: int, ry: int) -> str | None:
        """Find which widget is under root-coords (rx, ry)."""
        for key, eb in reversed(list(self._children.items())):
            x = getattr(eb, "_target_x", eb.get_allocation().x)
            y = getattr(eb, "_target_y", eb.get_allocation().y)
            w = eb.get_allocation().width
            h = eb.get_allocation().height
            if x <= rx <= x + w and y <= ry <= y + h:
                return key
        return None

    def _finish_drag(self, eb: Gtk.EventBox, key: str) -> None:
        self._dragging_key = None
        eb.set_opacity(1.0)
        self._set_cursor(eb, "grab")
        alloc = eb.get_allocation()
        if self._win_w > 1 and self._win_h > 1:
            position_manager.save_position(
                self._monitor_id,
                key,
                alloc.x / self._win_w,
                alloc.y / self._win_h,
            )

    def _set_cursor(self, eb: Gtk.EventBox, name: str | None) -> None:
        gdk_window = eb.get_window()
        if gdk_window is None:
            return
        if name:
            gdk_window.set_cursor(
                Gdk.Cursor.new_from_name(Gdk.Display.get_default(), name)
            )
        else:
            gdk_window.set_cursor(None)

    # edit mode
    def _on_edit_toggled(self, item) -> None:
        self._edit_mode = item.get_active()
        for key, eb in self._children.items():
            self._configure_eb_for_edit(eb, self._edit_mode)

    def _configure_eb_for_edit(self, eb: Gtk.EventBox, edit: bool) -> None:
        sc = eb.get_style_context()
        if edit:
            sc.add_class("edit-mode")
            self._set_cursor(eb, "grab")
        else:
            sc.remove_class("edit-mode")
            self._set_cursor(eb, None)

    # size allocate
    def _on_size_allocate(self, widget, alloc: Gdk.Rectangle) -> None:
        if not self._ready or self._in_size_allocate:
            return
        w, h = alloc.width, alloc.height
        if w < 1 or h < 1:
            return

        if w != self._old_w or h != self._old_h:
            is_first_real_size = self._old_w <= 1
            self._old_w = w
            self._old_h = h
            self._win_w = w
            self._win_h = h
            self._reposition_all()

            if is_first_real_size:
                self._fixed.set_opacity(0.0)
                self._fixed.show()
                self._fade_in()

    # positioning

    def _reposition_all(self) -> None:
        entries = position_manager.get_widgets(self._monitor_id)
        for entry in entries:
            key = entry["key"]
            eb = self._children.get(key)
            if eb is None:
                continue
            px = int(entry["px"] * self._win_w)
            py = int(entry["py"] * self._win_h)
            aw = eb.get_allocation().width or eb.get_preferred_width()[1]
            ah = eb.get_allocation().height or eb.get_preferred_height()[1]
            px = max(0, min(self._win_w - aw, px))
            py = max(0, min(self._win_h - ah, py))

            eb._target_x = px
            eb._target_y = py
            self._fixed.move(eb, px, py)

    # widget management

    def rebuild(self) -> None:
        for widget in self._children.values():
            self._fixed.remove(widget)
            widget.destroy()
        self._children.clear()

        entries = position_manager.get_widgets(self._monitor_id)
        for entry in entries:
            key = entry["key"]
            cls = DesktopWidgetRegistry.get_widget_class(key)
            if cls is None:
                logger.warning(f"[DesktopWidgetService] unknown widget key {key!r}")
                continue
            try:
                widget = cls()
                w_px, h_px = DesktopWidgetRegistry.get_widget_size(key)
                widget.set_size_request(w_px, h_px)

                eb = Gtk.EventBox()
                eb.set_size_request(w_px, h_px)
                eb.set_above_child(True)
                eb.add(widget)
                eb.show_all()

                self._fixed.put(eb, 0, 0)
                self._children[key] = eb
                if self._edit_mode:
                    self._configure_eb_for_edit(eb, True)
            except Exception as e:
                logger.error(f"[DesktopWidgetService] failed to build {key!r}: {e}")

        self._reposition_all()
        self._force_refresh()

    def add_widget(self, key: str, px: float = 0.02, py: float = 0.04) -> None:
        if key in self._children:
            return
        cls = DesktopWidgetRegistry.get_widget_class(key)
        if cls is None:
            return
        try:
            widget = cls()
            w_px, h_px = DesktopWidgetRegistry.get_widget_size(key)
            widget.set_size_request(w_px, h_px)

            eb = Gtk.EventBox()
            eb.set_size_request(w_px, h_px)
            eb.set_above_child(True)
            eb.add(widget)
            eb.show_all()

            self._fixed.put(eb, int(px * self._win_w), int(py * self._win_h))
            self._children[key] = eb
            if self._edit_mode:
                self._configure_eb_for_edit(eb, True)
            self._force_refresh()
        except Exception as e:
            logger.error(f"[DesktopWidgetService] failed to build {key!r}: {e}")

    def remove_widget(self, key: str) -> None:
        widget = self._children.pop(key, None)
        if widget:
            self._fixed.remove(widget)
            widget.destroy()

    def _force_refresh(self):
        self.hide()
        self.show_all()
        return False
