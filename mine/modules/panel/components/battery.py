from fabric.widgets.box import Box
from fabric.widgets.image import Image
from fabric.widgets.label import Label

from config.data import DATA
from services import BatteryService, DeviceState, has_config_changed, on_config_change


class Battery(Box):
    def __init__(self, **kwargs):
        self._load_config()
        self._icon = Image(icon_name="battery-100", icon_size=self._icon_size)
        self._label_widget = Label(label="")
        self._label_widget.set_no_show_all(True)

        super().__init__(
            name="battery",
            orientation="h",
            spacing=4,
            children=[self._icon, self._label_widget],
            **kwargs,
        )

        if not self._show_label:
            self._label_widget.hide()

        self._service = BatteryService()
        self._service.connect("changed", lambda *_: self._update())
        on_config_change(self._on_config_change)

        self._update()

    def _load_config(self):
        components = DATA()
        self._show_label = components["battery_label"]
        self._hide_on_full = components["battery_hide_on_full"]
        self._icon_size = components["battery_icon_size"]

    def _update(self):
        percentage = self._service.get_property("Percentage") or 0
        state = self._service.get_property("State") or 0

        is_full = int(percentage) >= 100 or DeviceState.get(state) in ("FULLY_CHARGED",)
        self.set_visible(not (self._hide_on_full and is_full))

        icon_name = self._resolve_icon_name(percentage, state)
        self._icon.set_from_icon_name(icon_name, self._icon_size)

        self._label_widget.set_visible(self._show_label)
        if self._show_label:
            self._label_widget.set_label(f"{int(percentage)}%")

    def _on_config_change(self, new_config, old_config):
        paths = [
            "panel.battery.enabled",
            "panel.battery.label",
            "panel.battery.hide_on_full",
            "panel.battery.icon_size",
        ]
        if any(has_config_changed(old_config, new_config, p) for p in paths):
            old_show_label = self._show_label
            old_hide_on_full = self._hide_on_full
            old_icon_size = self._icon_size
            self._load_config()
            if (
                old_show_label != self._show_label
                or old_hide_on_full != self._hide_on_full
                or old_icon_size != self._icon_size
            ):
                self._update()

    def _resolve_icon_name(self, percentage, state) -> str:
        pct = int(percentage)
        pct = max(0, min(100, pct))

        bucket = (pct // 10) * 10
        base = f"battery-{bucket:03d}"

        if state in {1, 4, 5}:  # CHARGING, FULLY_CHARGED, PENDING_CHARGE
            return f"{base}-charging"

        return f"{base}"
