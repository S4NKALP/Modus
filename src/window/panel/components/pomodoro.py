import os
from enum import Enum
from pathlib import Path

from fabric.utils import GLib, Gtk, exec_shell_command_async
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.circularprogressbar import CircularProgressBar
from fabric.widgets.label import Label

from shared.widgets.flat_scale import FlatScale
from shared.widgets.smooth_switch import SmoothSwitch
from shared.window.applet_window import AppletWindow
from utils.functions import format_mmss


class PomodoroState(Enum):
    STOPPED = 0
    FOCUS = 1
    SHORT_BREAK = 2
    LONG_BREAK = 3


class SettingsSpinner(Box):
    def __init__(self, value, min_val, max_val, callback, **kwargs):
        super().__init__(orientation="h", spacing=8, v_align="center", **kwargs)
        self.value = value
        self.min_val = min_val
        self.max_val = max_val
        self.callback = callback

        self.value_label = Label(label=str(self.value), name="pomodoro-spin-value")
        self.value_label.set_size_request(24, -1)

        up_icon = Label(label="▲")
        down_icon = Label(label="▼")

        up_btn = Button(child=up_icon, name="pomodoro-spin-btn")
        up_btn.connect("clicked", self._on_up)

        down_btn = Button(child=down_icon, name="pomodoro-spin-btn")
        down_btn.connect("clicked", self._on_down)

        btn_box = Box(orientation="v", spacing=0, children=[up_btn, down_btn])
        btn_box.set_name("pomodoro-spin-box")

        self.add(self.value_label)
        self.add(btn_box)

    def _on_up(self, *_):
        if self.value < self.max_val:
            self.value += 1
            self.value_label.set_label(str(self.value))
            if self.callback:
                self.callback()

    def _on_down(self, *_):
        if self.value > self.min_val:
            self.value -= 1
            self.value_label.set_label(str(self.value))
            if self.callback:
                self.callback()

    def get_value(self):
        return self.value


class Pomodoro(AppletWindow):
    def __init__(self, parent=None, pointing_to=None, **kwargs):
        super().__init__(
            parent=parent,
            pointing_to=pointing_to,
            layer="top",
            anchor="top right",
            margin="2px 10px 0px 0px",
            edge_margin=5,
            name="pomodoro-popup",
            title="modus-pomodoro",
            **kwargs,
        )

        self.state = PomodoroState.STOPPED
        self.current_cycle = 1

        # Default settings
        self.focus_mins = 25
        self.short_break_mins = 5
        self.long_break_mins = 15
        self.max_cycles = 4
        self.time_left = self.focus_mins * 60
        self.total_time = self.time_left

        self.is_running = False
        self.auto_start = True
        self.volume = 100

        self._timeout_id = None

        self._build_ui()
        self._update_display()

    def _build_ui(self):
        # Progress Bar and Timer Display
        self.time_label = Label(label="25:00", name="pomodoro-time")
        self.time_label.set_margin_bottom(5)
        self.cycle_label = Label(label="Cycle 1 / 4", name="pomodoro-cycle")

        timer_box = Box(
            orientation="v",
            v_align="center",
            h_align="center",
            children=[self.time_label, self.cycle_label],
        )

        self.progress_bar = CircularProgressBar(
            value=1.0,
            size=180,
            line_width=12,
            child=timer_box,
            name="pomodoro-progress",
        )

        self.phase_buttons = {}
        phase_box = Box(orientation="h", spacing=8, h_align="center")

        for phase in ["Focus", "Short Break", "Long Break"]:
            btn = Button(
                label=phase,
                name="pomodoro-phase-btn",
                on_clicked=lambda _, p=phase: self._switch_phase(p),
            )
            self.phase_buttons[phase] = btn
            phase_box.add(btn)

        header_box = Box(
            orientation="v",
            h_align="center",
            spacing=10,
            children=[phase_box, self.progress_bar],
        )
        header_box.set_margin_top(15)

        # Primary Buttons (Start/Pause, Reset)
        self.start_btn = Button(
            label="Start", name="pomodoro-start-btn", on_clicked=self.toggle_timer
        )
        self.reset_btn = Button(
            label="Reset", name="pomodoro-reset-btn", on_clicked=self.reset_timer
        )

        primary_btn_box = Box(
            orientation="h",
            spacing=10,
            h_align="center",
            children=[self.start_btn, self.reset_btn],
        )

        # Secondary Buttons (Skip, Restart)
        self.skip_btn = Button(
            label="Skip", name="pomodoro-secondary-btn", on_clicked=self.skip_session
        )
        self.restart_btn = Button(
            label="Restart",
            name="pomodoro-secondary-btn",
            on_clicked=self.restart_session,
        )

        secondary_btn_box = Box(
            orientation="h",
            spacing=50,
            h_align="center",
            children=[self.skip_btn, self.restart_btn],
        )
        secondary_btn_box.set_margin_bottom(15)
        secondary_btn_box.set_margin_top(5)

        # Settings
        self.focus_spin = SettingsSpinner(
            self.focus_mins, 1, 120, self._on_settings_changed
        )
        self.sbreak_spin = SettingsSpinner(
            self.short_break_mins, 1, 60, self._on_settings_changed
        )
        self.lbreak_spin = SettingsSpinner(
            self.long_break_mins, 1, 60, self._on_settings_changed
        )
        self.cycles_spin = SettingsSpinner(
            self.max_cycles, 1, 10, self._on_settings_changed
        )

        settings_list = Box(
            orientation="v",
            spacing=10,
            children=[
                self._setting_row("Focus", self.focus_spin, "min"),
                self._setting_row("Short Break", self.sbreak_spin, "min"),
                self._setting_row("Long Break", self.lbreak_spin, "min"),
                self._setting_row("Cycles", self.cycles_spin, ""),
            ],
        )
        settings_list.set_margin_bottom(15)

        # Options
        self.auto_start_switch = SmoothSwitch(
            name="settings-switch",
            active=self.auto_start,
            on_user_toggle=self._on_auto_start_toggled,
        )

        auto_start_box = Box(
            orientation="h",
            spacing=10,
            children=[
                Label(label="Auto-start next session", h_expand=True, h_align="start"),
                self.auto_start_switch,
            ],
        )
        auto_start_box.set_margin_bottom(10)

        # Volume
        self.volume_scale = FlatScale(
            min_value=0,
            max_value=100,
            value=self.volume,
            h_expand=True,
            on_value_changed=self._on_volume_changed,
        )
        self.volume_scale.set_size_request(-1, 30)
        self.volume_scale.add_style_class("flat-scale")

        volume_box = Box(
            orientation="h",
            spacing=10,
            children=[Label(label="Volume", h_align="start"), self.volume_scale],
        )

        main_box = Box(
            orientation="v",
            spacing=10,
            name="pomodoro-container",
            children=[
                header_box,
                primary_btn_box,
                secondary_btn_box,
                Gtk.Separator(),
                settings_list,
                Gtk.Separator(),
                auto_start_box,
                volume_box,
            ],
        )
        main_box.set_margin_left(20)
        main_box.set_margin_right(20)
        main_box.set_margin_bottom(20)

        self.children = main_box

    def _setting_row(self, label, widget, suffix):
        suffix_label = Label(label=suffix) if suffix else None
        widget_box = Box(orientation="h", spacing=5, children=[widget])
        if suffix_label:
            widget_box.add(suffix_label)

        return Box(
            orientation="h",
            children=[Label(label=label, h_expand=True, h_align="start"), widget_box],
        )

    def _on_settings_changed(self, *_):
        self.focus_mins = int(self.focus_spin.get_value())
        self.short_break_mins = int(self.sbreak_spin.get_value())
        self.long_break_mins = int(self.lbreak_spin.get_value())
        self.max_cycles = int(self.cycles_spin.get_value())

        if self.state == PomodoroState.STOPPED:
            self.reset_timer()
        self._update_display()

    def _on_auto_start_toggled(self, active: bool):
        self.auto_start = active

    def _on_volume_changed(self, widget, value):
        self.volume = value

    def toggle_timer(self, *_):
        if self.is_running:
            self.pause_timer()
        else:
            self.start_timer()

    def _switch_phase(self, phase):
        self.pause_timer()
        if phase == "Focus":
            self.state = PomodoroState.FOCUS
            self.total_time = self.focus_mins * 60
        elif phase == "Short Break":
            self.state = PomodoroState.SHORT_BREAK
            self.total_time = self.short_break_mins * 60
        elif phase == "Long Break":
            self.state = PomodoroState.LONG_BREAK
            self.total_time = self.long_break_mins * 60
        self.time_left = self.total_time
        self._update_display()

    def start_timer(self):
        if self.state == PomodoroState.STOPPED:
            self.state = PomodoroState.FOCUS
            self.total_time = self.focus_mins * 60
            self.time_left = self.total_time

        self.is_running = True
        self.start_btn.set_label("Pause")

        if self._timeout_id is None:
            self._timeout_id = GLib.timeout_add_seconds(1, self._tick)

    def pause_timer(self):
        self.is_running = False
        self.start_btn.set_label("Start")
        if self._timeout_id is not None:
            GLib.source_remove(self._timeout_id)
            self._timeout_id = None

    def reset_timer(self, *_):
        self.pause_timer()
        self.state = PomodoroState.STOPPED
        self.current_cycle = 1
        self.total_time = self.focus_mins * 60
        self.time_left = self.total_time
        self._update_display()

    def restart_session(self, *_):
        self.pause_timer()
        if self.state == PomodoroState.FOCUS:
            self.total_time = self.focus_mins * 60
        elif self.state == PomodoroState.SHORT_BREAK:
            self.total_time = self.short_break_mins * 60
        elif self.state == PomodoroState.LONG_BREAK:
            self.total_time = self.long_break_mins * 60
        else:
            self.total_time = self.focus_mins * 60
            self.state = PomodoroState.FOCUS

        self.time_left = self.total_time
        self._update_display()
        self.start_timer()

    def skip_session(self, *_):
        self.pause_timer()
        self._finish_session()

    def _tick(self):
        if not self.is_running:
            self._timeout_id = None
            return False

        if self.time_left > 0:
            self.time_left -= 1
            self._update_display()
            return True
        else:
            self._timeout_id = None
            self._finish_session()
            return False

    def _finish_session(self):
        if self.state == PomodoroState.FOCUS:
            if self.current_cycle >= self.max_cycles:
                self.state = PomodoroState.LONG_BREAK
                self.total_time = self.long_break_mins * 60
                exec_shell_command_async(
                    'notify-send "Pomodoro" "Focus session complete! Time for a long break."'
                )
            else:
                self.state = PomodoroState.SHORT_BREAK
                self.total_time = self.short_break_mins * 60
                exec_shell_command_async(
                    'notify-send "Pomodoro" "Focus session complete! Time for a short break."'
                )
        else:
            if self.state == PomodoroState.LONG_BREAK:
                self.current_cycle = 1
            else:
                self.current_cycle += 1

            self.state = PomodoroState.FOCUS
            self.total_time = self.focus_mins * 60
            exec_shell_command_async(
                'notify-send "Pomodoro" "Break over! Time to focus."'
            )

        self.play_sound()
        self.time_left = self.total_time
        self._update_display()

        if self.auto_start:
            self.start_timer()
        else:
            self.is_running = False
            self.start_btn.set_label("Start")
            self._timeout_id = None

    def play_sound(self):
        sound_file = ""
        base_dir = (
            Path(__file__).parent.parent.parent.parent
            / "assets"
            / "sounds"
            / "pomodoro"
        )

        if self.state == PomodoroState.FOCUS:
            sound_file = str(base_dir / "alert-work.mp3")
        elif self.state == PomodoroState.SHORT_BREAK:
            sound_file = str(base_dir / "alert-short-break.mp3")
        elif self.state == PomodoroState.LONG_BREAK:
            sound_file = str(base_dir / "alert-long-break.mp3")

        if os.path.exists(sound_file):
            vol = float(self.volume) / 100.0
            exec_shell_command_async(f"pw-play --volume={vol} '{sound_file}'")

    def _update_display(self):
        self.time_label.set_label(format_mmss(self.time_left, pad=True))
        self.cycle_label.set_label(f"Cycle {self.current_cycle} / {self.max_cycles}")

        progress = self.time_left / self.total_time if self.total_time > 0 else 0
        self.progress_bar.value = progress
        self.progress_bar.queue_draw()

        # Update phase button active states
        active_name = {
            PomodoroState.FOCUS: "Focus",
            PomodoroState.SHORT_BREAK: "Short Break",
            PomodoroState.LONG_BREAK: "Long Break",
        }.get(self.state, "Focus")

        for name, btn in self.phase_buttons.items():
            if name == active_name:
                btn.add_style_class("active")
            else:
                btn.remove_style_class("active")

        # Update progress bar color
        if self.state == PomodoroState.SHORT_BREAK:
            self.progress_bar.set_name("pomodoro-progress-short")
        elif self.state == PomodoroState.LONG_BREAK:
            self.progress_bar.set_name("pomodoro-progress-long")
        else:
            self.progress_bar.set_name("pomodoro-progress")
