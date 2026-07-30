from fabric.utils import GLib, logger, random
from fabric.widgets.box import Box
from fabric.widgets.eventbox import EventBox
from fabric.widgets.revealer import Revealer
from fabric.widgets.wayland import WaylandWindow as Window

from services.config import config, on_config_change
from services.modus import check_occlusion, get_modus_service

from .canvas import DockCanvas


class Dock(Window):
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
        self._occlusion_timer_id = None
        self._hyprland_handlers = []
        self._destroyed = False

        self.revealer.set_reveal_child(True)
        self.show_all()

        on_config_change(self._on_config_change)

        if config().get("dock.auto_hide", True):
            self._setup_occlusion_signals()
        self._check_occlusion_deferred()

    def _setup_occlusion_signals(self) -> None:
        """Subscribe to Hyprland events that affect occlusion."""
        hyprland = get_modus_service()._hyprland_connection
        events = [
            "event::openwindow",
            "event::closewindow",
            "event::movewindow",
            "event::workspace",
            "event::fullscreen",
        ]
        for event in events:
            handler_id = hyprland.connect(
                event, lambda *_: self._check_occlusion_deferred()
            )
            self._hyprland_handlers.append(handler_id)

    def _check_occlusion_deferred(self) -> None:
        """Debounce occlusion check to avoid rapid successive checks."""
        if hasattr(self, "_occlusion_check_pending") and self._occlusion_check_pending:
            return
        self._occlusion_check_pending = True
        GLib.timeout_add(50, self._run_occlusion_check)

    def _run_occlusion_check(self) -> bool:
        """Run the actual occlusion check."""
        self._occlusion_check_pending = False
        if self._destroyed:
            return False
        try:
            if not config().get("dock_auto_hide", True):
                return False
            is_occ = config().get("dock.always_occluded", False) or check_occlusion(
                ("bottom", self.dock_height)
            )
            if is_occ and not self.is_hovered and self.revealer.get_reveal_child():
                self.revealer.set_reveal_child(False)
            elif not is_occ and not self.revealer.get_reveal_child():
                self.revealer.set_reveal_child(True)
            elif is_occ and self.is_hovered:
                if not self.revealer.get_reveal_child():
                    self.revealer.set_reveal_child(True)
        except Exception as e:
            logger.error(f"[Dock] Occlusion check error: {e}")
        return False

    def _on_config_change(self, new_config, old_config) -> None:
        if config().has_changed("dock.enabled", old_config):
            self._update_visibility()

        if config().has_changed("dock.icon_size", old_config):
            self.canvas.update_icon_size()

        if config().has_changed("dock.auto_hide", old_config):
            if new_config.get("dock.auto_hide", True):
                self._setup_occlusion_signals()
            else:
                self._disconnect_occlusion_signals()
                self.revealer.set_reveal_child(True)

        if config().has_changed("dock.hide_special_workspace_apps", old_config):
            self.canvas._rebuild_model()

        if config().has_changed("dock.hover_scale", old_config):
            self.canvas.update_icon_size()

    def _update_visibility(self) -> None:
        if config().get("dock.enabled", True):
            self.show()
            self.revealer.set_reveal_child(True)
        else:
            self.hide()

    def on_hover_enter(self) -> None:
        self.is_hovered = True
        self.hide_ticket = random.getrandbits(32)
        self.revealer.set_reveal_child(True)

    def on_hover_leave(self) -> None:
        self.is_hovered = False
        ticket = random.getrandbits(32)
        self.hide_ticket = ticket

        def delayed_hide(t):
            if t == self.hide_ticket and not self.is_hovered:
                if config().get("dock.auto_hide", True):
                    is_occ = config().get(
                        "dock.always_occluded", False
                    ) or check_occlusion(("bottom", self.dock_height))
                    if is_occ:
                        self.revealer.set_reveal_child(False)
            return False

        GLib.timeout_add(500, delayed_hide, ticket)

    def _disconnect_occlusion_signals(self) -> None:
        """Disconnect all Hyprland occlusion signal handlers."""
        hyprland = get_modus_service()._hyprland_connection
        for handler_id in self._hyprland_handlers:
            try:
                hyprland.disconnect(handler_id)
            except Exception as e:
                logger.warning(f"[Dock] Error disconnecting occlusion handler: {e}")
        self._hyprland_handlers.clear()

    def destroy(self) -> None:
        self._destroyed = True
        self._disconnect_occlusion_signals()

        if hasattr(self, "canvas") and self.canvas:
            self.canvas.destroy()

        super().destroy()
