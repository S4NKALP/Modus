from fabric.widgets.circularprogressbar import CircularProgressBar
from utils.animator import Animator

class AnimatedCircularProgressBar(CircularProgressBar):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.animator = (
            Animator(
                bezier_curve=(0.15, 0.88, 0.68, 0.95),
                duration=0.8,
                min_value=self.min_value,
                max_value=self.value,
                tick_widget=self,
                notify_value=lambda p, *_: self.set_value(p.value),
            )
            .build()
            .play()
            .unwrap()
        )

    def animate_value(self, value: float):
        self.animator.pause()
        self.animator.min_value = self.value
        self.animator.max_value = value
        self.animator.play()
        return