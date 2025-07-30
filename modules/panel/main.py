from fabric.system_tray.widgets import SystemTray, SystemTrayItem
from fabric.utils import exec_shell_command, get_relative_path
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.datetime import DateTime
from fabric.widgets.label import Label
from fabric.widgets.revealer import Revealer
from gi.repository import Gtk
from fabric.widgets.svg import Svg
from modules.panel.components.indicators import Indicators
from modules.panel.components.menubar import MenuBar
from utils.wayland import WaylandWindow as Window

original_do_update_properties = SystemTrayItem.do_update_properties


def patched_do_update_properties(self, *_):
    # Try default GTK theme first
    icon_name = self._item.icon_name
    attention_icon_name = self._item.attention_icon_name

    if self._item.status == "NeedsAttention" and attention_icon_name:
        preferred_icon_name = attention_icon_name
    else:
        preferred_icon_name = icon_name

    # Try to load from default GTK theme
    if preferred_icon_name:
        try:
            default_theme = Gtk.IconTheme.get_default()
            if default_theme.has_icon(preferred_icon_name):
                pixbuf = default_theme.load_icon(
                    preferred_icon_name, self._icon_size, Gtk.IconLookupFlags.FORCE_SIZE
                )
                if pixbuf:
                    self._image.set_from_pixbuf(pixbuf)
                    # Set tooltip
                    tooltip = self._item.tooltip
                    self.set_tooltip_markup(
                        tooltip.description or tooltip.title or self._item.title.title()
                        if self._item.title
                        else "Unknown"
                    )
                    return
        except:
            pass
    original_do_update_properties(self, *_)


SystemTrayItem.do_update_properties = patched_do_update_properties


class Panel(Window):
    def __init__(self, **kwargs):
        super().__init__(
            name="bar",
            layer="top",
            anchor="left top right",
            exclusivity="auto",
            visible=False,
        )

        self.launcher = kwargs.get("launcher", None)
        self.menubar = MenuBar()

        self.imac = Button(
            name="panel-button",
            child=Svg(
                size=24,
                svg_file=get_relative_path("../../config/assets/icons/logo.svg"),
            ),
            on_clicked=lambda *_: self.menubar.show_system_dropdown(self.imac),
        )
        self.notch_spot = Box(
            name="notch-spot",
            size=(200, 24),
            h_expand=True,
            v_expand=True,
            children=Label(label="notch"),
        )

        self.tray = SystemTray(name="system-tray", spacing=4, icon_size=20)

        self.tray_revealer = Revealer(
            name="tray-revealer",
            child=self.tray,
            child_revealed=False,
            transition_type="slide-left",
            transition_duration=300,
        )

        self.chevron_button = Button(
            name="panel-button",
            child=Svg(
                size=18,
                svg_file=get_relative_path(
                    "../../config/assets/icons/chevron-right.svg"
                ),
            ),
            on_clicked=self.toggle_tray,
        )

        self.indicators = Indicators()

        self.search = Button(
            name="panel-button",
            on_clicked=lambda *_: self.search_apps(),
            child=Svg(
                size=20,
                svg_file=get_relative_path("../../config/assets/icons/search.svg"),
            ),
        )

        self.controlcenter = Button(
            name="panel-button",
            child=Svg(
                size=24,
                svg_file=get_relative_path(
                    "../../config/assets/icons/control-center.svg"
                ),
            ),
        )

        self.children = CenterBox(
            name="panel",
            start_children=Box(
                name="modules-left",
                children=[
                    self.imac,
                    self.menubar,
                ],
            ),
            # center_children=Box(
            #     name="modules-center",
            #     children=self.notch_spot,
            # ),
            end_children=Box(
                name="modules-right",
                spacing=4,
                orientation="h",
                children=[
                    self.tray_revealer,
                    self.chevron_button,
                    self.indicators,
                    self.search,
                    self.controlcenter,
                    DateTime(name="date-time", formatters=["%a %b %d %I:%M"]),
                ],
            ),
        )

        return self.show_all()

    def search_apps(self):
        self.launcher.show_launcher()

    def toggle_tray(self, *_):
        current_state = self.tray_revealer.child_revealed
        self.tray_revealer.child_revealed = not current_state

        if self.tray_revealer.child_revealed:
            self.chevron_button.get_child().set_from_file(
                get_relative_path("../../config/assets/icons/chevron-left.svg")
            )
        else:
            self.chevron_button.get_child().set_from_file(
                get_relative_path("../../config/assets/icons/chevron-right.svg")
            )
