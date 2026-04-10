from functools import partial

from fabric.widgets.scale import Scale

from shared.widgets.animator import Animator, cubic_bezier


class AnimatedScale(Scale):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.animator = (
            Animator(
                duration=0.8,
                timing_function=partial(cubic_bezier, 0.34, 1.56, 0.64, 1.0),
                min_value=self.min_value,
                max_value=self.value,
                tick_widget=self,
                notify_value=lambda anim: self.set_value(anim.value),
            )
            .build()
            .play()
            .unwrap()
        )

    def animate_value(self, value: float):
        if self.animator:
            self.animator.pause()
            self.animator.min_value = self.value
            self.animator.max_value = value
            self.animator.play()
