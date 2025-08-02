from gi.repository import GLib, Gtk
import gi
import math

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
            # Use 120 FPS for ultra-smooth animations like macOS
            self._timer_id = GLib.timeout_add(8, self._animate_all)  # 120 FPS

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

        # Process all animations in a single frame
        for widget in list(self._animating_widgets):
            if not widget._calculate_position():
                widgets_to_remove.append(widget)
            else:
                container = widget._get_container_for_redraw()
                if container:
                    self._containers_to_redraw.add(container)

        # Apply all position changes at once to prevent conflicts
        for widget in self._animating_widgets:
            widget._apply_position()

        # Batch redraw calls to minimize performance impact
        for container in self._containers_to_redraw:
            container.queue_draw()

        # Remove completed animations
        for widget in widgets_to_remove:
            self.remove_widget(widget)

        return len(self._animating_widgets) > 0  # Continue if widgets remain

    def get_active_widget_count(self):
        """Return the number of currently animating widgets"""
        return len(self._animating_widgets)

    def _get_optimal_interval(self):
        """Keep consistent 120 FPS for macOS-like smoothness"""
        return 8  # 120 FPS

    def _start_timer(self):
        interval = self._get_optimal_interval()
        self._timer_id = GLib.timeout_add(interval, self._animate_all)

    def _adjust_frame_rate(self):
        # No need to adjust frame rate anymore - keep it consistent
        pass


class MacOSEasing:
    """macOS-style easing functions for natural motion"""

    @staticmethod
    def ease_out_expo(t):
        """Exponential ease out - fast start, slow end"""
        return 1 - math.pow(2, -10 * t) if t != 1 else 1

    @staticmethod
    def ease_in_out_quart(t):
        """Quartic ease in-out for smooth acceleration/deceleration"""
        return 8 * t * t * t * t if t < 0.5 else 1 - math.pow(-2 * t + 2, 4) / 2

    @staticmethod
    def ease_out_back(t):
        """Back ease out for slight overshoot effect"""
        c1 = 1.70158
        c3 = c1 + 1
        return 1 + c3 * math.pow(t - 1, 3) + c1 * math.pow(t - 1, 2)

    @staticmethod
    def ease_out_cubic_bezier(t):
        """Custom cubic bezier similar to macOS default (0.25, 0.1, 0.25, 1.0)"""
        # Approximation of cubic-bezier(0.25, 0.1, 0.25, 1.0)
        return t * t * t * (t * (6 * t - 15) + 10)

    @staticmethod
    def ease_in_cubic(t):
        """Cubic ease in for smooth acceleration"""
        return t * t * t

    @staticmethod
    def ease_out_quint(t):
        """Quintic ease out for very smooth deceleration"""
        return 1 - math.pow(1 - t, 5)


class SlideRevealer(Gtk.Overlay):
    def __init__(self, child: Gtk.Widget, direction="right", duration=350, size=None):
        super().__init__()

        self.child = child
        self.direction = direction
        self.duration = duration  # Slightly faster for snappier feel
        self.fixed_size = size
        self._revealed = False
        self._animating = False
        self._start_time = None
        self._show_animation = False
        self._pending_position = None
        # Use float for sub-pixel positioning
        self._current_position = (0.0, 0.0)
        self._animation_id = None  # Track individual animation instances

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
        if self._revealed and not self._animating:
            return
        self._revealed = True
        self._start_animation(show=True)

    def hide(self):
        if not self._revealed and not self._animating:
            return
        self._revealed = False
        self._start_animation(show=False)

    def _start_animation(self, show: bool):
        # Stop any existing animation for this widget
        if self._animating:
            AnimationManager.get_instance().remove_widget(self)

        self._cached_dimensions = self._get_dimensions()
        if self._cached_dimensions[0] == 0 or self._cached_dimensions[1] == 0:
            self._animating = False
            return

        # Use high-precision monotonic time for smooth animations
        self._start_time = GLib.get_monotonic_time()
        self._animating = True
        self._show_animation = show
        self._animation_id = id(self)  # Unique ID for this animation instance

        if show:
            self.child.show()
            pos = self._get_offscreen_pos_cached()
            self._current_position = (float(pos[0]), float(pos[1]))
            self._fixed.move(self.child, int(pos[0]), int(pos[1]))

        AnimationManager.get_instance().add_widget(self)

    def _calculate_position(self):
        if not self._animating:
            return False

        elapsed = (GLib.get_monotonic_time() - self._start_time) / 1000
        t = min(elapsed / self.duration, 1.0)

        # Use different easing functions for better smoothness
        if self._show_animation:
            # Use quintic ease out for very smooth revealing
            eased = MacOSEasing.ease_out_quint(t)
        else:
            # Use cubic ease in for smooth hiding
            eased = MacOSEasing.ease_in_cubic(t)

        self._pending_position = self._get_position_at_progress_cached(eased)

        if t >= 1.0:
            self._animating = False
            self._cached_dimensions = None
            self._animation_id = None
            if not self._show_animation:
                GLib.idle_add(lambda: self.child.hide())
            return False
        return True

    def _apply_position(self):
        if self._pending_position:
            x, y = self._pending_position
            # Use sub-pixel positioning for smoother motion
            self._current_position = (x, y)
            # Round to nearest pixel for actual positioning
            pixel_x, pixel_y = int(round(x)), int(round(y))
            self._fixed.move(self.child, pixel_x, pixel_y)
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
                return -w + w * progress, 0.0
            elif self.direction == "right":
                return w - w * progress, 0.0
            elif self.direction == "top":
                return 0.0, -h + h * progress
            elif self.direction == "bottom":
                return 0.0, h - h * progress
        else:
            # Hiding animation: slide from onscreen (0,0) to offscreen
            if self.direction == "left":
                return -w * progress, 0.0  # Slide left (negative x)
            elif self.direction == "right":
                return w * progress, 0.0  # Slide right (positive x)
            elif self.direction == "top":
                return 0.0, -h * progress  # Slide up (negative y)
            elif self.direction == "bottom":
                return 0.0, h * progress  # Slide down (positive y)
        return 0.0, 0.0

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
            self._animation_id = None

    def destroy(self):
        self.stop_animation()
        super().destroy()
