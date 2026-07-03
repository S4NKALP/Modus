from fabric.utils import idle_add
from fabric.widgets.scrolledwindow import ScrolledWindow

from shared.widgets.animator import Animator


class AnimatedScrollable(ScrolledWindow):
    def __init__(
        self,
        bezier_curve: tuple[float, float, float, float] = (0.25, 0.1, 0.25, 1.0),
        duration: float = 0.3,
        animate: bool = True,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._last_req = -1
        self.animate = animate
        _, min_height = self.min_content_size
        _, max_height = self.max_content_size

        self.height_animator = Animator(
            bezier_curve=bezier_curve,
            duration=duration,
            min_value=min_height,
            max_value=max_height,
        )
        self.height_animator.connect("notify::value", self.on_animator_change)
        self.set_overlay_scrolling(True)

        self.connect("notify::child", self._on_child_notified)
        if self.get_child():
            self._on_child_notified()

    def _on_child_notified(self, *_):
        child = self.get_child()
        if child:
            child.connect("size-allocate", self._on_child_size_allocate)

    def _on_child_size_allocate(self, widget, allocation):
        _, nat_height = widget.get_preferred_height()
        target = min(nat_height, self.max_content_size[1])
        if target != self._last_req:
            self.animate_size(target)

    def on_animator_change(self, animator: Animator, *_):
        value = round(animator.value)
        self.set_min_content_height(value)
        self.queue_resize()

    def do_animate(
        self,
        from_height: int = 0,
        to_height: int = -1,
    ):
        if to_height == -1:
            return
        self.height_animator.pause()
        self.height_animator.min_value = from_height
        self.height_animator.max_value = to_height
        self.height_animator.play()
        return

    def animate_size(self, height: int = -1):
        if not self.animate:
            idle_add(lambda: self.snap_to_size(height))
            return
        self._last_req = height
        current_val = self.height_animator.value
        return self.do_animate(current_val, height)

    def snap_to_size(self, height: int):
        """Instantly resize without animation"""
        self._last_req = height
        self.height_animator.pause()
        self.height_animator.value = height
        self.set_min_content_height(height)
        self.queue_resize()

    def do_get_preferred_height(self):
        value = self.height_animator.value
        value = 0 if value < 0 else value
        return value, value
