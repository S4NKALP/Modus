from fabric import Fabricator
from fabric.utils import exec_shell_command
from fabric.widgets.box import Box
from snippets import MaterialIcon


class IdleIndicator(Box):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.idle_icon = self.create_idle_icon()
        self.fabricator = Fabricator(interval=1000, poll_from=self.check_idle_status)

        self.children = [self.idle_icon]

    def create_idle_icon(self):
        return MaterialIcon("coffee", 16)

    def check_idle_status(self, *_):
        output = exec_shell_command("pidof wayland-idle-inhibitor.py")
        is_idle = bool(str(output).strip())
        self.update_idle_status(is_idle)

    def update_idle_status(self, is_idle):
        if is_idle:
            self.idle_icon.set_visible(True)
        else:
            self.idle_icon.set_visible(False)
