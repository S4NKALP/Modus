# Author: Yousef EL-Darsh
# License (SPDX): AGPL-3.0-or-later

from functools import cache
from typing import Protocol, cast

from fabric.core.service import Property, Service, Signal
from fabric.utils import GLib, Gtk, clamp


@cache
def lerp(start: float, end: float, progress: float) -> float:
    return start + (end - start) * progress


@cache
def steps(n: int, progress: float, start_jump: bool = False) -> float:
    if start_jump:
        return min(int(progress * n), n - 1) / (n - 1) if n > 1 else 0.0
    return min(int(progress * n + 1e-10), n) / n


@cache
def cubic_bezier(
    x1: float, y1: float, x2: float, y2: float, progress: float, epsilon=1e-6
) -> float:
    # implementation yanked off of the internet, don't blame me about anything.
    # Fast-path boundaries to avoid overshoot and unnecessary work
    if progress <= 0.0 or progress >= 1.0:
        return clamp(progress, 0.0, 1.0)

    t_guess = progress
    for _ in range(8):
        t = t_guess
        t_sq = t * t
        omt = 1.0 - t
        omt_sq = omt * omt

        x = 3 * x1 * omt_sq * t + 3 * x2 * omt * t_sq + t * t_sq
        dx = 3 * x1 * omt_sq + 6 * (x2 - x1) * omt * t + 3 * (1 - x2) * t_sq

        if abs(dx) < epsilon:
            break

        delta = (x - progress) / dx
        t_guess -= delta
        t_guess = clamp(t_guess, 0.0, 1.0)

        if abs(delta) < epsilon:
            break

    t = clamp(t_guess, 0.0, 1.0)
    t_sq = t * t
    omt = 1.0 - t
    return 3 * y1 * omt * omt * t + 3 * y2 * omt * t_sq + t * t_sq


def ease_linear(progress: float) -> float:
    return cubic_bezier(1, 1, 0, 0, progress)


def ease_in(progress: float) -> float:
    return cubic_bezier(0.4, 0, 1, 1, progress)


def ease_out(progress: float) -> float:
    return cubic_bezier(0, 0, 0.2, 1, progress)


def ease_in_out(progress: float) -> float:
    return cubic_bezier(0.4, 0, 0.2, 1, progress)


class TimingFunctionCallback(Protocol):
    def __call__(self, progress: float, *args, **kwargs) -> float: ...


class Animator(Service):
    """
    An animator is a simple way for animating a value on
    a set timeline based on a given timing function
    """

    @Signal
    def finished(self) -> None: ...

    @Property(tuple[float, float, float, float], "read-write")
    def bezier_curve(self) -> tuple[float, float, float, float]:
        return self._bezier_curve

    @bezier_curve.setter
    def bezier_curve(self, value: tuple[float, float, float, float]):
        self._bezier_curve = value
        self._timing_function = lambda progress=0.0, **_: cubic_bezier(
            *value, progress=progress
        )
        return

    @Property(TimingFunctionCallback, "read-write")
    def timing_function(self) -> TimingFunctionCallback:
        return self._timing_function

    @timing_function.setter
    def timing_function(self, value: TimingFunctionCallback):
        self._timing_function = value
        return

    @Property(float, "read-write")
    def duration(self):
        return self._duration

    @duration.setter
    def duration(self, value: float):
        if value <= 0.0:
            raise ValueError("duration can't be smaller than or equal to 0.0")

        self._duration = value
        return

    @Property(float, "read-write")
    def value(self):
        return self._value

    @value.setter
    def value(self, value: float):
        self._value = value
        return

    @Property(float, "read-write")
    def max_value(self):
        return self._max_value

    @max_value.setter
    def max_value(self, value: float):
        self._max_value = value
        return

    @Property(float, "read-write")
    def min_value(self):
        return self._min_value

    @min_value.setter
    def min_value(self, value: float):
        self._min_value = value
        return

    @Property(bool, "read-write", default_value=False)
    def playing(self):
        return self._playing

    @playing.setter
    def playing(self, value: bool):  # this setter is intended for internal usage only
        self._playing = value
        return

    @Property(bool, "read-write", default_value=False)
    def repeat(self):
        return self._repeat

    @repeat.setter
    def repeat(self, value: bool):
        self._repeat = value
        return

    def __init__(
        self,
        duration: float = 0.8,
        timing_function: TimingFunctionCallback = ease_linear,
        value: float = 0.0,
        min_value: float = 0.0,
        max_value: float = 1.0,
        repeat: bool = False,
        tick_widget: Gtk.Widget | None = None,
        tick_interval: int = 16,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._playing = False
        self._value = value
        self._min_value = 0.0
        self._max_value = 1.0
        self._repeat = False
        self._duration = 0.8
        self._timing_function = timing_function
        self._tick_widget = tick_widget
        self._tick_interval = tick_interval

        self.timing_function = timing_function
        self.repeat = repeat
        self.duration = duration
        self.min_value = min_value
        self.max_value = max_value
        self.value = value
        self.playing = False

        self._start_time = None
        self._tick_handler = None
        self._timeline_pos = 0.0

    def do_get_time_now(self):
        return GLib.get_monotonic_time() / 1_000_000

    def do_update_value(self, delta_time: float):
        if not self._playing:
            return

        elapsed_time = delta_time - cast(float, self._start_time)

        self._timeline_pos = min(1.0, elapsed_time / self._duration)

        self.value = lerp(
            self._min_value,
            self._max_value,
            self._timing_function(progress=self._timeline_pos),
        )

        if not self._timeline_pos >= 1.0:
            return

        if not self._repeat:
            # all done..
            self.value = self._max_value
            self.finished()
            self.pause()
            return

        self._start_time = delta_time
        self._timeline_pos = 0.0
        return

    def do_handle_tick(self, *_):
        current_time = self.do_get_time_now()
        self.do_update_value(current_time)
        return True

    def do_remove_tick_handlers(self):
        if not self._tick_handler:
            return

        if self._tick_widget:
            self._tick_widget.remove_tick_callback(self._tick_handler)
        else:
            GLib.source_remove(self._tick_handler)
        self._tick_handler = None
        return

    def play(self):
        if self._playing:
            return

        self.playing = True
        self._start_time = self.do_get_time_now()

        if self._tick_handler:
            return

        if self._tick_widget:
            self._tick_handler = self._tick_widget.add_tick_callback(
                self.do_handle_tick
            )
            return

        self._tick_handler = GLib.timeout_add(self._tick_interval, self.do_handle_tick)
        return

    def pause(self):
        self.playing = False
        return self.do_remove_tick_handlers()

    def stop(self):
        if not self._tick_handler:
            self._timeline_pos = 0
            self.playing = False
            return
        return self.do_remove_tick_handlers()
