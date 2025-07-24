from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label
from fabric.widgets.stack import Stack
from fabric.widgets.revealer import Revealer
from fabric.widgets.centerbox import CenterBox
import utils.icons as icons
from fabric.utils.helpers import exec_shell_command_async


class Tile(Box):
    def __init__(self, *, menu: bool, markup: str, label: str, props: Label, **kwargs):
        default_classes = ["tile"]
        extra_classes = kwargs.pop("style_classes", [])
        merged_classes = default_classes + extra_classes
        super().__init__(style_classes=merged_classes, v_align="start", **kwargs)
        self.props = props
        self.icon = Label(style_classes="tile-icon", markup=markup)
        self.tile_label = Label(
            style_classes="tile-label", label=label, h_align="start"
        )
        self.toggle = False

        self.type_box = Box(
            style_classes="tile-type",
            orientation="v",
            v_expand=True,
            h_expand=True,
            v_align="center",
            children=[self.tile_label, self.props],
        )

        self.menu_button = Button(
            style_classes="tile-button",
            h_expand=True,
            child=Label(style_classes="tile-icon", markup=icons.arrow_head),
            on_clicked=self.handle_click,
        )

        self.content_button = None

        if menu:
            self.content_button = Revealer(
                transition_duration=150,
                transition_type="slide-left",
                h_expand=True,
                child=Box(children=[self.type_box, self.menu_button]),
                child_revealed=True,
            )
        else:
            self.content_button = Revealer(
                transition_duration=150,
                transition_type="slide-left",
                child=Box(children=[self.type_box]),
                child_revealed=True,
            )

        self.normal_view = Box(
            children=[self.icon, self.content_button],
        )

        self.menu = Button(
            style_classes="tile-menu",
            child=Label(label="hi!"),
            on_clicked=self.handle_click,
        )

        self.stack = Stack(
            transition_type="crossfade",
            transition_duration=150,
            h_expand=True,
            children=[self.normal_view, self.menu],
        )

        self.children = self.stack

    def handle_click(self, source):
        if self.toggle:
            self.toggle = False
            self.menu.add_style_class("contract")
            self.menu.remove_style_class("expand")
            self.stack.set_visible_child(self.normal_view)
        else:
            self.toggle = True
            self.stack.set_visible_child(self.menu)
            self.menu.add_style_class("expand")
            self.menu.remove_style_class("contract")
        print(self.toggle, self.get_name())
        name = self.get_name()
        exec_shell_command_async(
            f"fabric-cli exec bar-example \"notch.dashboard.handle_tile_menu_expand('{
                name
            }', {self.toggle})\""
        )

    def mini_view(self):
        self.content_button.set_reveal_child(False)
        self.icon.set_h_expand(True)
        self.content_button.set_h_expand(False)
        self.add_style_class("mini")

    def maxi_view(self):
        self.content_button.set_reveal_child(True)
        self.icon.set_h_expand(False)
        self.content_button.set_h_expand(True)
        self.remove_style_class("mini")


class TileSpecial(Box):
    def __init__(self, *, mini_props, props, **kwargs):
        super().__init__(**kwargs)
        self.props = props
        self.mini_props = mini_props
        self.toggle = False

        self.content_button = None

        self.normal_view = Box(
            children=self.props,
        )
        self.collapsed_view = Box(children=self.mini_props)

        self.stack = Stack(
            transition_type="crossfade",
            transition_duration=150,
            h_expand=True,
            v_align="start",
            children=[self.normal_view, self.collapsed_view],
        )

        self.children = self.stack

    def mini_view(self):
        self.normal_view.set_style("margin:-999px")
        self.collapsed_view.set_style("margin:0px;")
        self.stack.set_visible_child(self.collapsed_view)

    def maxi_view(self):
        self.collapsed_view.set_style("margin:-999px")
        self.normal_view.set_style("margin:0px;")
        self.stack.set_visible_child(self.normal_view)
