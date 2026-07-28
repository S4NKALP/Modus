import importlib
import os
import pkgutil
import sys
from functools import partial

import cairo
import tomlkit
from fabric.utils import Gdk, Gio, GLib, Gtk, logger
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

_CONFIG_DESKTOP_DIR = os.path.join(
    os.path.dirname(toml_file("desktop.toml")), "desktop"
)
_TARGET = Gtk.TargetEntry.new("text/plain", Gtk.TargetFlags.SAME_APP, 0)


_user_widget_modules: dict[str, str] = {}
_user_key_to_file: dict[str, str] = {}


def _load_user_widgets() -> set[str]:
    """Import every .py in config/desktop/. Returns set of loaded keys."""
    if not os.path.isdir(_CONFIG_DESKTOP_DIR):
        return set()
    loaded_keys: set[str] = set()
    for fname in os.listdir(_CONFIG_DESKTOP_DIR):
        if not fname.endswith(".py") or fname.startswith("_"):
            continue
        module_name = fname[:-3]
        full_path = os.path.join(_CONFIG_DESKTOP_DIR, fname)
        try:
            before_keys = set(DesktopWidgetRegistry.keys())
            spec = importlib.util.spec_from_file_location(
                f"user_widget_{module_name}", full_path
            )
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod
            spec.loader.exec_module(mod)
            _user_widget_modules[module_name] = spec.name
            new_keys = set(DesktopWidgetRegistry.keys()) - before_keys
            for k in new_keys:
                _user_key_to_file[k] = module_name
                DesktopWidgetRegistry.register_user(k)
            loaded_keys.update(new_keys)
        except Exception as e:
            logger.error(f"[DesktopWidgets] failed to load user widget {fname}: {e}")
    return loaded_keys


_load_user_widgets()


class PositionManager:
    """Merges widget defaults from registry with user overrides in desktop.toml.

    config/desktop/*.py widgets register themselves with a default position.
    desktop.toml stores drag-and-drop overrides per monitor.
    """

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
        if mid_str not in state or not state[mid_str]:
            state[mid_str] = []
            for key in DesktopWidgetRegistry.widgets():
                pos = DesktopWidgetRegistry.get_default_position(key)
                px, py = pos if pos else (0.0, 0.0)
                state[mid_str].append({"key": key, "px": px, "py": py})
            cls._write(state)
        else:
            registered = set(DesktopWidgetRegistry.keys())
            before = len(state[mid_str])
            state[mid_str] = [e for e in state[mid_str] if e["key"] in registered]
            for key in registered - {e["key"] for e in state[mid_str]}:
                pos = DesktopWidgetRegistry.get_default_position(key)
                px, py = pos if pos else (0.0, 0.0)
                state[mid_str].append({"key": key, "px": px, "py": py})
            if len(state[mid_str]) != before:
                cls._write(state)
        return list(state[mid_str])

    @classmethod
    def save_position(cls, monitor_id: int, key: str, px: float, py: float) -> None:
        state = cls._read()
        mid_str = str(monitor_id)
        if mid_str not in state:
            state[mid_str] = []
        for entry in state[mid_str]:
            if entry["key"] == key:
                entry["px"] = round(max(0.0, min(1.0, px)), 5)
                entry["py"] = round(max(0.0, min(1.0, py)), 5)
                break
        else:
            state[mid_str].append({"key": key, "px": round(px, 5), "py": round(py, 5)})
        cls._write(state)

    @classmethod
    def remove_override(cls, monitor_id: int, key: str) -> None:
        """Remove a drag/drop override so the widget reverts to its default position."""
        state = cls._read()
        mid_str = str(monitor_id)
        if mid_str not in state:
            return
        state[mid_str] = [e for e in state[mid_str] if e["key"] != key]
        cls._write(state)


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
        self._ready = False
        self._in_size_allocate = False
        self._edit_mode = False

        self._dragging_key: str | None = None
        self._dragging_eb: Gtk.EventBox | None = None
        self._drag_drop_success: bool = False
        self._input_rebuild_pending: bool = False

        self._root = Box(h_expand=True, v_expand=True)
        self._root.add(self._fixed)

        monitor = Gdk.Display.get_default().get_monitor(monitor_id)
        if monitor:
            geom = monitor.get_geometry()
            self._win_w = max(1, geom.width)
            self._win_h = max(1, geom.height)

        self._fade_in_animator = self._make_fade_animator(1.0)
        self._fade_out_animator = self._make_fade_animator(0.0)
        self._fixed.set_opacity(0.0)

        super().__init__(
            monitor=monitor_id,
            anchor="left right top bottom",
            exclusivity="none",
            layer="bottom",
            child=self._root,
            keyboard_mode="none",
            visible=True,
            name=f"desktop-widgets-{monitor_id}",
        )

        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect("size-allocate", self._on_size_allocate)
        self.connect("button-press-event", self._on_window_button_press)
        self._setup_drag_dest()
        self._setup_file_monitor()
        self._last_user_files: set[str] = set()
        GLib.timeout_add(2000, self._poll_user_widgets)

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

    def _make_fade_animator(self, target_opacity: float) -> Animator:
        animator = Animator(
            bezier_curve=(0.4, 0.0, 0.2, 1.0),
            duration=0.2,
            min_value=0.0,
            max_value=1.0,
            tick_widget=self._root,
        )
        animator.connect("notify::value", self._on_fade_value)
        animator.connect("finished", partial(self._on_fade_finished, target_opacity))
        return animator

    def _on_fade_value(self, animator, _) -> None:
        self._fixed.set_opacity(animator.value)

    def _on_fade_finished(self, target_opacity: float, _animator) -> None:
        self._fixed.set_opacity(target_opacity)

    def _fade_in(self) -> None:
        if self._fade_in_animator.playing:
            return
        self._fade_out_animator.pause()
        opacity = self._fixed.get_opacity()
        self._fade_in_animator.value = opacity
        self._fade_in_animator.min_value = opacity
        self._fade_in_animator.max_value = 1.0
        self._fade_in_animator.play()

    def _fade_out(self) -> None:
        self._fade_in_animator.pause()
        opacity = self._fixed.get_opacity()
        self._fade_out_animator.min_value = 0.0
        self._fade_out_animator.max_value = opacity
        self._fade_out_animator.value = opacity
        self._fade_out_animator.play()

    # fallback poll — catches deletions that Gio file monitor misses

    def _poll_user_widgets(self) -> bool:
        if not os.path.isdir(_CONFIG_DESKTOP_DIR):
            return True
        current = {
            f[:-3]
            for f in os.listdir(_CONFIG_DESKTOP_DIR)
            if f.endswith(".py") and not f.startswith("_")
        }
        if current != self._last_user_files:
            self._last_user_files = current
            stale = {k for k, f in _user_key_to_file.items() if f not in current}
            if stale:
                logger.info(f"[DesktopWidgets] poll found stale: {stale}")
                for key in stale:
                    mod_name = _user_key_to_file.pop(key, None)
                    if mod_name:
                        sys.modules.pop(f"user_widget_{mod_name}", None)
                        _user_widget_modules.pop(mod_name, None)
                DesktopWidgetRegistry.unregister_user_keys(stale)
                _load_user_widgets()
                self.rebuild()
        return True

    # file monitor — live-rebuild when config/desktop/ changes

    def _setup_file_monitor(self) -> None:
        if not os.path.isdir(_CONFIG_DESKTOP_DIR):
            os.makedirs(_CONFIG_DESKTOP_DIR, exist_ok=True)
        config_dir = Gio.File.new_for_path(_CONFIG_DESKTOP_DIR)
        monitor = config_dir.monitor_directory(Gio.FileMonitorFlags.NONE, None)
        monitor.connect("changed", self._on_config_changed)
        self._config_monitor = monitor

    def _on_config_changed(self, _monitor, _file, _other, event_type) -> None:
        logger.info(f"[DesktopWidgets] file monitor event: {event_type}")
        if event_type in (
            Gio.FileMonitorEvent.CREATED,
            Gio.FileMonitorEvent.DELETED,
            Gio.FileMonitorEvent.CHANGED,
        ):
            GLib.idle_add(self._on_widget_dir_changed)

    def _on_widget_dir_changed(self) -> bool:
        current_files = {
            f[:-3]
            for f in os.listdir(_CONFIG_DESKTOP_DIR)
            if f.endswith(".py") and not f.startswith("_")
        }
        stale_keys = {k for k, f in _user_key_to_file.items() if f not in current_files}
        logger.info(
            f"[DesktopWidgets] dir changed: current={current_files}, "
            f"stale={stale_keys}, tracked={set(_user_key_to_file.keys())}"
        )
        for key in stale_keys:
            mod_name = _user_key_to_file.pop(key, None)
            if mod_name:
                sys.modules.pop(f"user_widget_{mod_name}", None)
                _user_widget_modules.pop(mod_name, None)
        DesktopWidgetRegistry.unregister_user_keys(stale_keys)
        _load_user_widgets()
        self.rebuild()
        return False

    # right-click context menu

    def _on_window_button_press(self, widget, event: Gdk.EventButton) -> bool:
        if event.button == 3:
            self._show_context_menu(event)
            return True
        return False

    def _show_context_menu(self, event: Gdk.EventButton) -> None:
        menu = Gtk.Menu()

        label_text = "Done Edit" if self._edit_mode else "Edit Widgets"
        edit_item = Gtk.CheckMenuItem(label=label_text)
        edit_item.set_active(self._edit_mode)
        edit_item.connect("toggled", self._on_edit_toggled)
        menu.append(edit_item)

        menu.show_all()
        menu.popup_at_pointer(event)

    # edit mode

    def _on_edit_toggled(self, item) -> None:
        self._edit_mode = item.get_active()
        for key, eb in self._children.items():
            sc = eb.get_style_context()
            if self._edit_mode:
                sc.add_class("edit-mode")
                self._setup_applet_drag(eb, key)
            else:
                sc.remove_class("edit-mode")
                eb.drag_source_unset()

    # GTK DnD

    def _setup_drag_dest(self) -> None:
        self.drag_dest_set(
            Gtk.DestDefaults.ALL,
            [_TARGET],
            Gdk.DragAction.MOVE,
        )
        target_list = self.drag_dest_get_target_list()
        if target_list:
            target_list.add_text_targets(0)
        self.connect("drag-motion", self._on_drag_motion)
        self.connect("drag-leave", self._on_drag_leave)
        self.connect("drag-data-received", self._on_drag_data_received)

    def _setup_applet_drag(self, eb: Gtk.EventBox, key: str) -> None:
        eb.drag_source_set(
            Gdk.ModifierType.BUTTON1_MASK,
            [_TARGET],
            Gdk.DragAction.MOVE,
        )
        target_list = eb.drag_source_get_target_list()
        if target_list:
            target_list.add_text_targets(0)
        eb.connect("drag-begin", self._on_applet_drag_begin, key)
        eb.connect("drag-data-get", self._on_applet_drag_data_get, key)
        eb.connect("drag-end", self._on_applet_drag_end, key)

    def _on_applet_drag_begin(self, eb, ctx, key: str) -> None:
        self._dragging_key = key
        self._dragging_eb = eb
        self._drag_drop_success = False

    def _on_applet_drag_data_get(self, eb, ctx, data_obj, info, time, key: str) -> None:
        data_obj.set_text(f"widget:{key}", -1)

    def _on_applet_drag_end(self, eb, ctx, key: str) -> None:
        if not self._drag_drop_success:
            self._fixed.remove(eb)
            self._fixed.put(
                eb,
                getattr(eb, "_target_x", 0),
                getattr(eb, "_target_y", 0),
            )
        self._dragging_key = None
        self._dragging_eb = None
        self._schedule_input_rebuild()

    def _on_drag_motion(self, widget, ctx, x, y, time) -> bool:
        targets = [t.name() for t in ctx.list_targets()]
        if "text/plain" not in targets or self._dragging_key is None:
            Gdk.drag_status(ctx, 0, time)
            return True
        eb = self._dragging_eb
        if eb is not None:
            aw = eb.get_allocation().width or eb.get_preferred_width()[1]
            ah = eb.get_allocation().height or eb.get_preferred_height()[1]
            nx = max(0, min(self._win_w - aw, int(x - aw / 2)))
            ny = max(0, min(self._win_h - ah, int(y - ah / 2)))
            self._fixed.move(eb, nx, ny)
        Gdk.drag_status(ctx, Gdk.DragAction.MOVE, time)
        return True

    def _on_drag_leave(self, widget, ctx, time) -> None:
        pass

    def _on_drag_data_received(self, widget, ctx, x, y, data, info, time) -> None:
        payload = (data.get_text() or "") if data else ""
        if not payload.startswith("widget:"):
            Gtk.drag_finish(ctx, False, False, time)
            return

        key = payload.split(":", 1)[1]
        eb = self._children.get(key)
        if eb is None:
            Gtk.drag_finish(ctx, False, False, time)
            return

        aw = eb.get_allocation().width or eb.get_preferred_width()[1]
        ah = eb.get_allocation().height or eb.get_preferred_height()[1]
        new_x = max(0, min(self._win_w - aw, int(x - aw / 2)))
        new_y = max(0, min(self._win_h - ah, int(y - ah / 2)))

        eb._target_x = new_x
        eb._target_y = new_y

        if self._win_w > 1 and self._win_h > 1:
            position_manager.save_position(
                self._monitor_id,
                key,
                new_x / self._win_w,
                new_y / self._win_h,
            )

        self._fixed.remove(eb)
        self._fixed.put(eb, new_x, new_y)
        eb.show()

        self._drag_drop_success = True
        Gtk.drag_finish(ctx, True, False, time)
        self._schedule_input_rebuild()

    # size allocate

    def do_size_allocate(self, alloc):
        Gtk.Window.do_size_allocate(self, alloc)
        self._schedule_input_rebuild()

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
            self._force_refresh()
            self._schedule_input_rebuild()

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
            self._fixed.remove(eb)
            self._fixed.put(eb, px, py)

    # widget management

    def rebuild(self) -> None:
        self._dragging_eb = None
        self._dragging_key = None

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
                eb.add(widget)
                eb.show_all()

                self._fixed.put(eb, 0, 0)
                self._children[key] = eb
            except Exception as e:
                logger.error(f"[DesktopWidgetService] failed to build {key!r}: {e}")

        self._reposition_all()
        self._force_refresh()
        self._schedule_input_rebuild()

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
            eb.add(widget)
            eb.show_all()

            self._fixed.put(eb, int(px * self._win_w), int(py * self._win_h))
            self._children[key] = eb
            self._schedule_input_rebuild()
        except Exception as e:
            logger.error(f"[DesktopWidgetService] failed to build {key!r}: {e}")

    def remove_widget(self, key: str) -> None:
        widget = self._children.pop(key, None)
        if widget:
            self._fixed.remove(widget)
            widget.destroy()
            self._schedule_input_rebuild()

    def _force_refresh(self):
        self._in_size_allocate = True
        self.hide()
        self.show_all()
        self._in_size_allocate = False
        return False

    # partial input region — only widget areas capture events, empty desktop passes through

    def _schedule_input_rebuild(self) -> None:
        if self._input_rebuild_pending:
            return
        self._input_rebuild_pending = True
        GLib.idle_add(self._do_input_rebuild)

    def _do_input_rebuild(self) -> bool:
        self._input_rebuild_pending = False
        self._rebuild_input_region()
        return False

    def _rebuild_input_region(self) -> None:
        rects = []
        for eb in self._children.values():
            a = eb.get_allocation()
            if a.width > 0 and a.height > 0:
                rects.append(cairo.RectangleInt(a.x, a.y, a.width, a.height))
        if not rects:
            self.input_shape_combine_region(
                cairo.Region(cairo.RectangleInt(0, 0, 0, 0))
            )
            return
        region = cairo.Region(rects[0])
        for rect in rects[1:]:
            region.union(cairo.Region(rect))
        self.input_shape_combine_region(region)
