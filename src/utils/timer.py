"""Managed GLib timer helper.

Replaces the repeated schedule/cancel/cleanup pattern::

    if self._timer_id:
        GLib.source_remove(self._timer_id)
    self._timer_id = GLib.timeout_add(ms, self._on_timeout)

    # in destroy():
    if self._timer_id:
        GLib.source_remove(self._timer_id)

Usage::

    self._hide_timer = ManagedTimer()
    # schedule
    self._hide_timer.schedule(DISPLAY_MS, self._do_hide)
    # cancel
    self._hide_timer.cancel()
    # cleanup in destroy()
    self._hide_timer.cancel()
"""

from fabric.utils import GLib


class ManagedTimer:
    """A single-shot GLib timer that auto-cancels any pending source."""

    __slots__ = ("_source_id",)

    def __init__(self):
        self._source_id: int | None = None

    def schedule(self, milliseconds: int, callback) -> None:
        """Schedule *callback* after *milliseconds*.

        If a timer is already pending it is cancelled first.
        """
        self.cancel()
        self._source_id = GLib.timeout_add(milliseconds, self._on_fire, callback)

    def _on_fire(self, callback):
        self._source_id = None
        callback()
        return False  # one-shot

    def cancel(self) -> None:
        """Cancel the pending timer, if any."""
        if self._source_id is not None:
            GLib.source_remove(self._source_id)
            self._source_id = None

    @property
    def is_pending(self) -> bool:
        return self._source_id is not None
