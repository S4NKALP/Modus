from fabric.utils import Gdk, logger


class PullToRefreshMixin:
    def setup_pull_to_refresh(self, scrolled_widget):
        self._scrolled_widget = scrolled_widget
        self.vadjustment = scrolled_widget.get_vadjustment()
        self.pull_start_y = 0
        self.is_pulling = False
        self.pull_threshold = 50
        self._anim_finished_handler = None

        scrolled_widget.connect("scroll-event", self.on_scroll_event)
        scrolled_widget.connect("button-press-event", self.on_button_press)
        scrolled_widget.connect("button-release-event", self.on_button_release)
        scrolled_widget.connect("motion-notify-event", self.on_motion_notify)

        scrolled_widget.set_events(
            Gdk.EventMask.SCROLL_MASK
            | Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )

    def on_scroll_event(self, widget, event):
        if self.vadjustment.get_value() <= 0:
            if event.direction == Gdk.ScrollDirection.UP:
                self._trigger_scan()
                self._trigger_refresh()
                return True
        return False

    def on_button_press(self, widget, event):
        if self.vadjustment.get_value() <= 0:
            self.pull_start_y = event.y
            self.is_pulling = True
        return False

    def on_button_release(self, widget, event):
        if self.is_pulling:
            pull_distance = event.y - self.pull_start_y
            if pull_distance > self.pull_threshold:
                self._trigger_scan()
                self._trigger_refresh()
            self.refresh_indicator.set_visible(False)
            self.refresh_indicator.remove_style_class("ready-to-refresh")
            self.is_pulling = False
        return False

    def on_motion_notify(self, widget, event):
        if self.is_pulling and self.vadjustment.get_value() <= 0:
            pull_distance = event.y - self.pull_start_y
            if pull_distance > 0:
                self.refresh_indicator.set_visible(True)
                if pull_distance >= self.pull_threshold:
                    self.refresh_indicator.set_label(self._get_pull_ready_label())
                    self.refresh_indicator.add_style_class("ready-to-refresh")
                else:
                    self.refresh_indicator.set_label(self._get_pull_normal_label())
                    self.refresh_indicator.remove_style_class("ready-to-refresh")
            else:
                self.refresh_indicator.set_visible(False)
        return False

    def _cancel_pending_refresh(self):
        if hasattr(self, "_anim_finished_handler") and self._anim_finished_handler:
            try:
                self._scrolled_widget.height_animator.disconnect(
                    self._anim_finished_handler
                )
            except Exception as e:
                logger.warning(
                    f"[pull-to-refresh] height_animator.disconnect(...) failed: {e}"
                )
            self._anim_finished_handler = None

    def _refresh_after_animation(self):
        if self._destroyed:
            return False
        anim = self._scrolled_widget.height_animator
        if anim.playing:
            self._anim_finished_handler = anim.connect(
                "finished",
                lambda *_: self._trigger_refresh() if not self._destroyed else None,
            )
        else:
            self._trigger_refresh()
        return False

    def _get_pull_normal_label(self):
        return "↓ Pull to refresh"

    def _get_pull_ready_label(self):
        return "↑ Release to refresh"

    def _trigger_scan(self):
        raise NotImplementedError

    def _trigger_refresh(self):
        raise NotImplementedError
