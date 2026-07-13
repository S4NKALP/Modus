from fabric.utils import Gdk, GLib
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from fabric.widgets.wayland import WaylandWindow as Window

from services.screencapture import screen_capture_service
from window.screencapture.options_menu import OptionsMenu
from window.screencapture.tool_button import ToolButton, ToolGroup


class ScreenCaptureWindow(Window):
    _TOOLS = [
        ("region.svg", "Screenshot Region", "screenshot-region"),
        ("monitor.svg", "Screenshot Screen", "screenshot-screen"),
        ("window.svg", "Screenshot Window", "screenshot-window"),
        ("region-video.svg", "Record Region", "record-region"),
        ("monitor-video.svg", "Record Screen", "record-screen"),
        ("window-video.svg", "Record Window", "record-window"),
    ]

    def __init__(self, **kwargs):
        super().__init__(
            name="sc-window",
            title="modus-screencapture",
            anchor="bottom",
            layer="top",
            keyboard_mode="on-demand",
            margin="0px 0px 120px 0px",
            visible=False,
            **kwargs,
        )

        self._tool_group = ToolGroup()
        self._options_menu: OptionsMenu | None = None
        self._delay_timeout_id: int | None = None

        close_lbl = Label(label="✕")
        close_btn = Button(name="sc-close-btn", child=close_lbl)
        close_btn.connect("clicked", lambda *_: self.hide())

        tool_boxes = []
        for i, (icon, tip, tid) in enumerate(self._TOOLS):
            if i == 3:
                tool_boxes.append(Box(name="sc-separator"))
            btn = ToolButton(
                icon=icon, tooltip=tip, tool_id=tid, group=self._tool_group
            )
            self._tool_group.add(btn)
            tool_boxes.append(btn)

        self._tool_bar = Box(
            name="sc-tool-bar",
            orientation="h",
            spacing=2,
            children=tool_boxes,
        )

        # Options button — opens a Gtk.Menu
        self._options_btn = Button(name="sc-options-btn")
        opt_inner = Box(
            orientation="h",
            spacing=2,
            children=[
                Label(name="sc-options-label", label="Options"),
                Label(name="sc-options-arrow", label="⌄"),
            ],
        )
        self._options_btn.add(opt_inner)
        self._options_btn.connect("clicked", self._toggle_options)

        # Action button
        self._action_btn = Button(name="sc-action-btn", label="Capture")
        self._action_btn.connect("clicked", self._on_action)

        # Assemble toolbar
        toolbar = Box(
            name="sc-toolbar",
            orientation="h",
            spacing=0,
            children=[
                close_btn,
                self._tool_bar,
                self._options_btn,
                self._action_btn,
            ],
        )

        # Wrap in a transparent container to prevent solid square background issues
        container = Box(
            name="sc-container",
            orientation="v",
            h_align="center",
            v_align="center",
            expand=True,
            children=[toolbar],
        )

        self.add(container)

        self._tool_group.select_id("screenshot-screen")
        self._tool_group.on_change(self._on_tool_changed)

        screen_capture_service.connect("recording-started", self._on_recording_started)
        screen_capture_service.connect("recording-stopped", self._on_recording_stopped)

        self.connect("key-press-event", self._on_key_press)

    def do_focus(self, direction):
        """
        Disable GTK's built-in Tab/Shift+Tab focus traversal so those keys
        reach our key-press-event handler instead of moving widget focus.
        """
        return False

    def _on_key_press(self, _, event: Gdk.EventKey) -> bool:
        kv = event.keyval
        mods = event.state

        # Escape — close window
        if kv == Gdk.KEY_Escape:
            self.hide()
            return True

        # Enter / Space — trigger action
        if kv in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
            self._on_action()
            return True

        # Left / h — previous tool (clamp)
        if kv in (Gdk.KEY_Left, Gdk.KEY_h):
            idx = self._tool_group.current_index()
            self._tool_group.select_index(max(0, idx - 1))
            return True

        # Right / l — next tool (clamp)
        if kv in (Gdk.KEY_Right, Gdk.KEY_l):
            idx = self._tool_group.current_index()
            self._tool_group.select_index(min(len(self._TOOLS) - 1, idx + 1))
            return True

        # Shift+Tab — previous tool (wrap)
        if kv in (Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab) and (
            mods & Gdk.ModifierType.SHIFT_MASK
        ):
            idx = self._tool_group.current_index()
            self._tool_group.select_index((idx - 1) % len(self._TOOLS))
            return True

        # Tab — next tool (wrap)
        if kv == Gdk.KEY_Tab:
            idx = self._tool_group.current_index()
            self._tool_group.select_index((idx + 1) % len(self._TOOLS))
            return True

        # 1–6 — jump directly to tool
        if Gdk.KEY_1 <= kv <= Gdk.KEY_6:
            self._tool_group.select_index(kv - Gdk.KEY_1)
            return True

        return False

    def _toggle_options(self, *_):
        if self._options_menu is None:
            self._options_menu = OptionsMenu()
        self._options_menu.popup_below(self._options_btn)

    def _on_tool_changed(self, tool_id: str):
        is_recording_tool = tool_id.startswith("record-")
        is_active = screen_capture_service.is_recording

        ctx = self._action_btn.get_style_context()
        if is_active:
            self._action_btn.set_label("Stop")
            ctx.add_class("recording")
        elif is_recording_tool:
            self._action_btn.set_label("Record")
            ctx.remove_class("recording")
        else:
            self._action_btn.set_label("Capture")
            ctx.remove_class("recording")

    def _on_action(self, *_):
        # Stop an active recording
        if screen_capture_service.is_recording:
            screen_capture_service.stop_recording()
            return

        delay = 0
        if self._options_menu:
            delay = self._options_menu.get_timer_delay()

        self.hide()

        if delay > 0:
            self._delay_timeout_id = GLib.timeout_add_seconds(delay, self._do_action)
        else:
            GLib.timeout_add(80, self._do_action)

    def _do_action(self):
        tool = self._tool_group.selected_id
        self._delay_timeout_id = None

        # Gather options once
        use_audio = (
            self._options_menu.get_mic_enabled() if self._options_menu else False
        )
        show_cursor = (
            self._options_menu.get_show_cursor() if self._options_menu else False
        )

        if tool == "screenshot-screen":
            self._do_screenshot("active")
        elif tool == "screenshot-window":
            self._do_screenshot("window")  # hyprshot -m window
        elif tool == "screenshot-region":
            self._do_screenshot("region")
        elif tool == "record-screen":
            screen_capture_service.record(
                "active", use_audio=use_audio, show_cursor=show_cursor
            )
        elif tool == "record-window" or tool == "record-region":
            screen_capture_service.record(
                "selection", use_audio=use_audio, show_cursor=show_cursor
            )

        return False

    def _do_screenshot(self, target: str):
        """
        Take a screenshot.
        - On success: service emits screenshot_taken(path)  → we stay hidden.
        - On cancel:  service emits screenshot_taken(None)  → we re-show.
        - If screenshot() itself fails immediately           → we re-show.
        The handler is always disconnected after one fire to avoid leaks.
        """
        # Gather options
        output_dir = None
        show_cursor = False
        if self._options_menu:
            output_dir = self._options_menu.get_save_dir()
            show_cursor = self._options_menu.get_show_cursor()

        _handler_id = [None]

        def _on_taken(svc, path, *_):
            # Disconnect immediately — one-shot
            if _handler_id[0] is not None:
                try:
                    svc.disconnect(_handler_id[0])
                except Exception:
                    pass
                _handler_id[0] = None
            # Re-show only on cancel (path is None)
            if not path:
                GLib.timeout_add(120, self.show)

        _handler_id[0] = screen_capture_service.connect("screenshot-taken", _on_taken)

        def _safe_disconnect():
            if _handler_id[0] is not None:
                try:
                    screen_capture_service.disconnect(_handler_id[0])
                except Exception:
                    pass
                _handler_id[0] = None
            return False

        # Safety net: disconnect if the service never emits (e.g. capture failed
        # silently), otherwise the one-shot handler would leak on every shot.
        GLib.timeout_add_seconds(10, _safe_disconnect)

        ok = screen_capture_service.screenshot(
            target,
            output_dir=output_dir,
            show_cursor=show_cursor,
        )
        if not ok:
            # screenshot() returned False — clean up and re-show immediately
            if _handler_id[0] is not None:
                try:
                    screen_capture_service.disconnect(_handler_id[0])
                except Exception:
                    pass
                _handler_id[0] = None
            GLib.timeout_add(120, self.show)

    def _on_recording_started(self, *_):
        self._action_btn.set_label("Stop")
        self._action_btn.get_style_context().add_class("recording")
        self.hide()

    def _on_recording_stopped(self, *_):
        tool = self._tool_group.selected_id or ""
        ctx = self._action_btn.get_style_context()
        self._action_btn.set_label(
            "Record" if tool.startswith("record-") else "Capture"
        )
        ctx.remove_class("recording")

    def toggle(self, ss: str | None = None, sr: str | None = None):
        """
        Toggle the window, or trigger a direct action via CLI.
        :param ss: screenshot mode (e.g. 'region', 'fullscreen', 'selectwindow')
        :param sr: record mode (e.g. 'region', 'fullscreen', 'selectwindow')
        """
        if ss:
            target_map = {
                "region": "region",
                "fullscreen": "active",
                "selectwindow": "window",
            }
            self.hide()
            target = target_map.get(ss, ss)
            screen_capture_service.screenshot(target)
            return

        if sr:
            if screen_capture_service.is_recording:
                screen_capture_service.stop_recording()
                return

            target_map = {
                "region": "selection",
                "fullscreen": "active",
                "selectwindow": "selection",
            }
            use_audio = (
                self._options_menu.get_mic_enabled() if self._options_menu else False
            )
            show_cursor = (
                self._options_menu.get_show_cursor() if self._options_menu else False
            )
            screen_capture_service.record(
                target_map.get(sr, sr),
                use_audio=use_audio,
                show_cursor=show_cursor,
            )
            return

        if self.get_visible():
            self.hide()
        else:
            self.show()
