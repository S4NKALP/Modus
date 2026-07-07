from fabric.utils import Gdk, Gtk
from shared.widgets.smooth_switch import SmoothSwitch


class SwitchMenuItem(Gtk.MenuItem):
    """
    A Gtk.MenuItem that contains a label + SmoothSwitch side by side.
    Clicking the row toggles the switch.
    """

    def __init__(self, label: str, active: bool = True):
        super().__init__()
        self.set_name("sc-menu-item")

        self._switch = SmoothSwitch(
            active=active,
            width=34,
            height=18,
            style_classes=["sc-switch"],
            v_align="center",
        )

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        row.set_hexpand(True)

        lbl = Gtk.Label(label=label)
        lbl.set_halign(Gtk.Align.START)
        lbl.set_hexpand(True)
        row.pack_start(lbl, True, True, 0)
        row.pack_end(self._switch, False, False, 0)
        row.show_all()

        self.add(row)
        self.connect("activate", self._on_activate)

    def _on_activate(self, *_):
        # Toggle the switch when the menu item is clicked
        self._switch._on_click(self._switch, type("e", (), {"button": 1})())

    def get_active(self) -> bool:
        return self._switch.get_active()

    def set_active(self, value: bool):
        self._switch.set_active(value)


class OptionsMenu:
    """
    Gtk.Menu that pops up below the Options button.
    Contains: Save to, Timer, Microphone, and toggle options.
    State is preserved across opens.
    """

    _TIMER_LABELS = ["None", "5 seconds", "10 seconds"]
    _MIC_LABELS = ["None", "Built-in Microphone"]

    def __init__(self):
        self._timer_idx = 0
        self._mic_idx = 0
        self._menu = Gtk.Menu()
        self._menu.set_name("sc-menu")

        self._add_section("Save to")
        self._save_path = "~/Pictures/Screenshots"
        save_item = Gtk.MenuItem()
        save_item.set_name("sc-menu-item")
        save_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._save_lbl = Gtk.Label(label=self._save_path)
        self._save_lbl.set_halign(Gtk.Align.START)
        self._save_lbl.set_hexpand(True)
        browse_lbl = Gtk.Label(label="Other…")
        browse_lbl.get_style_context().add_class("sc-menu-hint")
        save_box.pack_start(self._save_lbl, True, True, 0)
        save_box.pack_end(browse_lbl, False, False, 0)
        save_box.show_all()
        save_item.add(save_box)
        save_item.connect("activate", self._choose_save_dir)
        self._menu.append(save_item)

        self._add_separator()

        self._timer_hint_lbl = Gtk.Label(label=self._TIMER_LABELS[0])
        self._timer_hint_lbl.get_style_context().add_class("sc-menu-hint")
        timer_parent = self._make_submenu_item("Timer", self._timer_hint_lbl)
        timer_sub = Gtk.Menu()
        timer_sub.set_name("sc-menu")
        self._timer_items: list[Gtk.CheckMenuItem] = []
        for i, lbl in enumerate(self._TIMER_LABELS):
            item = Gtk.CheckMenuItem(label=lbl)
            item.set_name("sc-menu-item")
            item.set_draw_as_radio(True)
            item.set_active(i == 0)
            item.connect("activate", self._on_timer_select, i)
            timer_sub.append(item)
            self._timer_items.append(item)
        timer_sub.show_all()
        timer_parent.set_submenu(timer_sub)
        self._menu.append(timer_parent)

        self._add_separator()

        self._mic_hint_lbl = Gtk.Label(label=self._MIC_LABELS[0])
        self._mic_hint_lbl.get_style_context().add_class("sc-menu-hint")
        mic_parent = self._make_submenu_item("Microphone", self._mic_hint_lbl)
        mic_sub = Gtk.Menu()
        mic_sub.set_name("sc-menu")
        self._mic_items: list[Gtk.CheckMenuItem] = []
        for i, lbl in enumerate(self._MIC_LABELS):
            item = Gtk.CheckMenuItem(label=lbl)
            item.set_name("sc-menu-item")
            item.set_draw_as_radio(True)
            item.set_active(i == 0)
            item.connect("activate", self._on_mic_select, i)
            mic_sub.append(item)
            self._mic_items.append(item)
        mic_sub.show_all()
        mic_parent.set_submenu(mic_sub)
        self._menu.append(mic_parent)

        self._add_separator()

        self._add_section("Options")
        self._floating_thumb = SwitchMenuItem("Show Floating Thumbnail", active=True)
        self._remember_sel = SwitchMenuItem("Remember Last Selection", active=True)
        self._show_mouse = SwitchMenuItem("Show Mouse Pointer", active=True)
        self._menu.append(self._floating_thumb)
        self._menu.append(self._remember_sel)
        self._menu.append(self._show_mouse)

        self._menu.show_all()

    def _make_submenu_item(self, label: str, hint_lbl: Gtk.Label) -> Gtk.MenuItem:
        """
        Create a menu item that has a label on the left and a dim hint on the right.
        The hint shows the currently selected sub-option.
        """
        item = Gtk.MenuItem()
        item.set_name("sc-menu-item")
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        row.set_hexpand(True)

        title = Gtk.Label(label=label)
        title.set_halign(Gtk.Align.START)
        title.set_hexpand(True)

        hint_lbl.set_halign(Gtk.Align.END)
        hint_lbl.show()

        row.pack_start(title, True, True, 0)
        row.pack_end(hint_lbl, False, False, 0)
        row.show_all()
        item.add(row)
        return item

    def _add_section(self, text: str):
        item = Gtk.MenuItem()
        item.set_name("sc-menu-item")
        item.set_sensitive(False)
        lbl = Gtk.Label(label=text.upper())
        lbl.set_name("sc-menu-section")
        lbl.set_halign(Gtk.Align.START)
        lbl.show()
        item.add(lbl)
        self._menu.append(item)

    def _add_separator(self):
        sep = Gtk.SeparatorMenuItem()
        sep.set_name("sc-menu-sep")
        self._menu.append(sep)

    def _on_timer_select(self, item, idx: int):
        if not item.get_active():
            return
        self._timer_idx = idx
        self._timer_hint_lbl.set_label(self._TIMER_LABELS[idx])
        for i, t in enumerate(self._timer_items):
            if i != idx:
                t.set_active(False)

    def _on_mic_select(self, item, idx: int):
        if not item.get_active():
            return
        self._mic_idx = idx
        self._mic_hint_lbl.set_label(self._MIC_LABELS[idx])
        for i, m in enumerate(self._mic_items):
            if i != idx:
                m.set_active(False)

    def _choose_save_dir(self, *_):
        dialog = Gtk.FileChooserDialog(
            title="Choose Save Location",
            action=Gtk.FileChooserAction.SELECT_FOLDER,
        )
        dialog.add_buttons(
            "_Cancel",
            Gtk.ResponseType.CANCEL,
            "_Select",
            Gtk.ResponseType.ACCEPT,
        )
        resp = dialog.run()
        if resp == Gtk.ResponseType.ACCEPT:
            self._save_path = dialog.get_filename()
            self._save_lbl.set_label(self._save_path)
        dialog.destroy()

    def popup_below(self, widget: Gtk.Widget):
        """Pop the menu up, positioned below the given widget."""
        self._menu.popup_at_widget(
            widget,
            Gdk.Gravity.SOUTH_WEST,
            Gdk.Gravity.NORTH_WEST,
            None,
        )

    def get_timer_delay(self) -> int:
        return [0, 5, 10][self._timer_idx]

    def get_mic_enabled(self) -> bool:
        """True when a microphone source (not None) is selected."""
        return self._mic_idx != 0

    def get_save_dir(self) -> str | None:
        """
        Returns the custom save directory if the user changed it,
        or None to use the service default.
        """
        default = "~/Pictures/Screenshots"
        return self._save_path if self._save_path != default else None

    def get_show_cursor(self) -> bool:
        return self._show_mouse.get_active()

    def get_show_thumbnail(self) -> bool:
        return self._floating_thumb.get_active()

    def get_remember_selection(self) -> bool:
        return self._remember_sel.get_active()
