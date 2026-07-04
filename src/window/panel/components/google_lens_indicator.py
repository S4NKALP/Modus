from fabric.widgets.button import Button

from services.google_lens import GoogleLens
from utils.functions import thread
from utils.utils import setup_cursor_hover, svg_file


class GoogleLensIndicator(Button):
    def __init__(self, **kwargs):
        super().__init__(name="panel-button", **kwargs)
        self._lens = GoogleLens.get_initial()

        self.icon = svg_file("google-lens.svg", size=16)
        self.add(self.icon)

        setup_cursor_hover(self, "pointer")
        self.connect("clicked", self.on_clicked)

    def on_clicked(self, *_):
        thread(self._lens.search)
