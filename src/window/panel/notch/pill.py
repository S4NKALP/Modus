from fabric.widgets.box import Box
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.shapes import Corner


class NotchPill(Box):
    def __init__(self, center_widget, v_align="center", **kwargs):
        super().__init__(
            name="panel-notch-wrap",
            orientation="h",
            spacing=0,
            v_align=v_align,
            h_align="center",
            h_expand=False,
            **kwargs,
        )
        self.left_corner = Corner(
            name="panel-notch-corner",
            orientation="top-right",
            size=20,
            h_align="start",
            v_align="start",
        )
        self.right_corner = Corner(
            name="panel-notch-corner",
            orientation="top-left",
            size=20,
            h_align="end",
            v_align="start",
        )
        self.center_widget = center_widget
        self.notch_box = CenterBox(
            name="panel-notch",
            orientation="h",
            h_align="center",
            v_align="center",
            start_children=self.left_corner,
            center_children=center_widget,
            end_children=self.right_corner,
        )
        self.add(self.notch_box)
