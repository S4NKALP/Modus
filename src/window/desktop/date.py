from fabric.widgets.box import Box
from fabric.widgets.datetime import DateTime
from gi.repository import Gtk

from window.desktop.registry import DesktopWidgetRegistry


class _DraggableDateTime(DateTime):
    """DateTime subclass that lets button-press events propagate to the parent
    EventBox so GTK drag-and-drop works across the entire widget area.

    GtkButton's class handler (do_button_press_event) returns True at
    G_SIGNAL_RUN_FIRST, which stops the accumulator before DateTime's own
    connected handler ever runs.  Both must return False for the event to
    reach the EventBox where drag_source_set lives.

    It also avoids the GtkButton label visibility glitch: calling
    set_label() on every tick destroys and recreates the internal child
    label, and after enough redraws GTK3 stops showing it.  Instead the
    internal label is captured once and updated in place via set_text().
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        child = self.get_child()
        if isinstance(child, Gtk.Label):
            self._text_label = child

    def do_update_label(self):
        text = self.do_format()
        label = getattr(self, "_text_label", None)
        if label is None:
            return super().do_update_label()
        label.set_text(text)
        return True

    def do_button_press_event(self, event):
        match event.button:
            case 1:
                self.do_cycle_next()
            case 3:
                self.do_cycle_prev()
        return False

    def do_handle_press(self, _widget, _event, *_args):
        return False


class DesktopDateWidget(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="date-widget",
            h_expand=True,
            v_expand=True,
            justification="center",
            h_align="center",
            v_align="start",
            orientation="v",
            **kwargs,
        )
        self.top = Box(orientation="h", name="date-top", h_expand=True)
        # Update interval is generous (100s) since the date only changes
        # daily; _DraggableDateTime updates its label in place so the
        # frequent set_label() glitch that drops label visibility in GTK3
        # is avoided entirely.
        date_interval = 100000
        self.dateone = _DraggableDateTime(
            formatters=["%a"], interval=date_interval, name="day"
        )
        self.datetwo = _DraggableDateTime(
            formatters=["%b"], interval=date_interval, name="month"
        )
        self.datethree = _DraggableDateTime(
            formatters=["%-d"], interval=date_interval, name="date"
        )
        self.top.add(self.dateone)
        self.top.add(self.datetwo)
        self.add(self.top)
        self.add(self.datethree)


class DesktopDateContainer(Box):
    def __init__(self, **kwargs):
        super().__init__(
            orientation="v",
            name="date-container",
            v_expand=True,
            size=(170, 170),
            v_align="center",
            h_align="center",
            children=[DesktopDateWidget()],
            **kwargs,
        )


DesktopWidgetRegistry.register(
    "date", DesktopDateContainer, (174, 174), (0.00573, 0.00949)
)
