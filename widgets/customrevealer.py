from gi.repository import GLib, Gtk
import gi

gi.require_version("Gtk", "3.0")

# TODO: UsE BETTER APPROACH IF POSSIBLE


class AnimationManager:
    _instance = None
    _animating_widgets = set()
    _timer_id = None
    _containers_to_redraw = set()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def add_widget(self, widget):
        self._animating_widgets.add(widget)
        if self._timer_id is None:
            self._timer_id = GLib.timeout_add(22, self._animate_all)  # 45 FPS

    def remove_widget(self, widget):
        self._animating_widgets.discard(widget)
        if not self._animating_widgets and self._timer_id:
            # Stop timer when no widgets are animating
            GLib.source_remove(self._timer_id)
            self._timer_id = None
            # Clear any pending redraws
            self._containers_to_redraw.clear()

    def _animate_all(self):
        # Clear previous frame's redraw queue
        self._containers_to_redraw.clear()

        widgets_to_remove = []
        for widget in list(self._animating_widgets):
            if not widget._calculate_position():
                widgets_to_remove.append(widget)
            else:
                container = widget._get_container_for_redraw()
                if container:
                    self._containers_to_redraw.add(container)

        # Apply all position changes at once
        for widget in self._animating_widgets:
            widget._apply_position()

        # Single redraw call per container
        for container in self._containers_to_redraw:
            container.queue_draw()

        # Remove completed animations
        for widget in widgets_to_remove:
            self.remove_widget(widget)

        return len(self._animating_widgets) > 0  # Continue if widgets remain

    def _get_optimal_interval(self):
        """Calculate optimal frame interval based on widget count"""
        widget_count = len(self._animating_widgets)
        if widget_count <= 1:
            return 16  # 60 FPS
        elif widget_count <= 2:
            return 16  # 60 FPS
        elif widget_count <= 4:
            return 22  # 45 FPS
        elif widget_count <= 6:
            return 33  # 30 FPS
        else:
            return 50  # 20 FPS

    def _start_timer(self):
        interval = self._get_optimal_interval()
        self._timer_id = GLib.timeout_add(interval, self._animate_all)

    def _adjust_frame_rate(self):
        if not self._timer_id:
            return

        new_interval = self._get_optimal_interval()
        GLib.source_remove(self._timer_id)
        self._timer_id = GLib.timeout_add(new_interval, self._animate_all)


class SlideRevealer(Gtk.Overlay):
    def __init__(self, child: Gtk.Widget, direction="right", duration=600, size=None):
        super().__init__()

        self.child = child
        self.direction = direction
        self.duration = duration
        self.fixed_size = size
        self._revealed = False
        self._animating = False
        self._start_time = None
        self._show_animation = False
        self._pending_position = None

        self._fixed = Gtk.Fixed()
        self._fixed.set_has_window(False)
        self._fixed.add(child)
        self.add_overlay(self._fixed)

        if self.fixed_size:
            self.set_size_request(self.fixed_size[0], self.fixed_size[1])
            child.hide()
            self.show_all()
        else:
            child.connect("size-allocate", self._on_size_allocate)
            child.hide()
            self.show_all()

    def _on_size_allocate(self, _widget, allocation):
        if not self.fixed_size:
            current_req = self.get_size_request()
            if (
                current_req[0] != allocation.width
                or current_req[1] != allocation.height
            ):
                self.set_size_request(allocation.width, allocation.height)

    def set_reveal_child(self, reveal: bool):
        if reveal:
            self.reveal()
        else:
            self.hide()

    def reveal(self):
        if self._revealed or self._animating:
            return
        self._revealed = True
        self._start_animation(show=True)

    def hide(self):
        if not self._revealed or self._animating:
            return
        self._revealed = False
        self._start_animation(show=False)

    def _start_animation(self, show: bool):
        if self._animating:
            AnimationManager.get_instance().remove_widget(self)

        self._cached_dimensions = self._get_dimensions()
        if self._cached_dimensions[0] == 0 or self._cached_dimensions[1] == 0:
            self._animating = False
            return

        self._start_time = GLib.get_monotonic_time()
        self._animating = True
        self._show_animation = show

        if show:
            self.child.show()
            self._fixed.move(self.child, *self._get_offscreen_pos_cached())

        AnimationManager.get_instance().add_widget(self)

    def _calculate_position(self):
        if not self._animating:
            return False

        elapsed = (GLib.get_monotonic_time() - self._start_time) / 1000
        t = min(elapsed / self.duration, 1.0)

        if self._show_animation:
            # Ease out quadratic (no bounce/overshoot)
            eased = 1 - (1 - t) ** 2
        else:
            eased = t**2  # Ease in quadratic for hide animation

        self._pending_position = self._get_position_at_progress_cached(eased)

        if t >= 1.0:
            self._animating = False
            self._cached_dimensions = None
            if not self._show_animation:
                GLib.idle_add(lambda: self.child.hide())
            return False
        return True

    def _apply_position(self):
        if self._pending_position:
            x, y = self._pending_position
            self._fixed.move(self.child, x, y)
            self._pending_position = None

    def _get_container_for_redraw(self):
        return self

    def _get_dimensions(self):
        if self.fixed_size:
            return self.fixed_size
        else:
            alloc = self.child.get_allocation()
            return alloc.width, alloc.height

    def _get_offscreen_pos_cached(self):
        w, h = self._cached_dimensions
        if self.direction == "left":
            return -w, 0
        elif self.direction == "right":
            return w, 0
        elif self.direction == "top":
            return 0, -h
        elif self.direction == "bottom":
            return 0, h
        return 0, 0

    def _get_position_at_progress_cached(self, progress):
        w, h = self._cached_dimensions
        if self._show_animation:
            # Showing animation: slide from offscreen to onscreen (0,0)
            if self.direction == "left":
                return int(-w + w * progress), 0
            elif self.direction == "right":
                return int(w - w * progress), 0
            elif self.direction == "top":
                return 0, int(-h + h * progress)
            elif self.direction == "bottom":
                return 0, int(h - h * progress)
        else:
            # Hiding animation: slide from onscreen (0,0) to offscreen
            if self.direction == "left":
                return int(-w * progress), 0  # Slide left (negative x)
            elif self.direction == "right":
                return int(w * progress), 0  # Slide right (positive x)
            elif self.direction == "top":
                return 0, int(-h * progress)  # Slide up (negative y)
            elif self.direction == "bottom":
                return 0, int(h * progress)  # Slide down (positive y)
        return 0, 0

    def set_slide_direction(self, direction):
        self.direction = direction

    def is_revealed(self):
        return self._revealed

    def is_animating(self):
        return self._animating

    def get_child_revealed(self):
        return self._revealed

    def stop_animation(self):
        if self._animating:
            AnimationManager.get_instance().remove_widget(self)
            self._animating = False
            self._cached_dimensions = None

    def destroy(self):
        self.stop_animation()
        super().destroy()
