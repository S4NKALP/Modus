from fabric.utils import logger
from fabric.widgets.box import Box
from fabric.widgets.label import Label

from services.weather import Weather as WeatherServiceBackend
from utils.gtk_utils import svg_file
from window.desktop.registry import DesktopWidgetRegistry


class DesktopWeatherWidget(Box):
    def __init__(self, parent=None, **kwargs):
        super().__init__(
            name="weather-container",
            h_expand=True,
            v_expand=True,
            visible=True,
            all_visible=True,
            justification="right",
            orientation="v",
            **kwargs,
        )
        self.inner = Box(
            name="weather-widget",
            orientation="v",
            h_expand=True,
            v_expand=True,
            visible=True,
            all_visible=True,
        )
        self.add(self.inner)
        self.weatherinfo = None
        self._create_labels()
        self._layout_labels()

        self._service = WeatherServiceBackend.get_default()
        self._service.connect("notify::is-loading", self._on_service_update)
        self._service.connect("notify::temperature", self._on_service_update)
        self._service.connect("notify::weather-icon", self._on_service_update)
        self._service.connect("notify::weather-description", self._on_service_update)
        self._service.connect("notify::location", self._on_service_update)
        self._service.connect("notify::daily-forecast", self._on_service_update)
        self._service.connect("notify::weather-gradient", self._on_service_update)
        self._on_service_update(self._service, None)

    def _create_labels(self):
        self.header = Box(orientation="h", h_expand=True)
        self.body = Box(orientation="v", v_expand=True, valign="end")

        self.city = Label(
            name="city",
            label="Loading...",
            justification="left",
            h_align="start",
            max_chars_width=15,
            ellipsization="end",
        )
        self.temperature = Label(name="temperature", label="--°", h_align="start")
        self.condition_em = svg_file(
            "weather/weather-none-available.svg", size=(35, 35), name="condition-emoji"
        )
        self.condition = Label(
            name="condition",
            label="Loading...",
            max_chars_width=18,
            ellipsization="end",
            h_align="start",
        )
        self.feels_like = Label(name="feels-like", label="L:-- H:--", h_align="start")

    def _layout_labels(self):
        self.header.add(self.city)
        self.header.pack_end(self.condition_em, False, False, 0)
        self.body.add(self.temperature)
        self.body.add(self.condition)
        self.body.add(self.feels_like)
        self.inner.add(self.header)
        self.inner.add(self.body)

    def _on_service_update(self, *args):
        if self._service.is_loading:
            return

        if self._service.has_error:
            self.city.set_label("Error")
            self.condition.set_label("Unavailable")
            self.add_style_class("weather-clear")
            return

        try:
            icon_name = self._service.weather_icon or "weather-none-available"
            temp_val = self._service.temperature
            temp = f"{round(float(temp_val))}°" if temp_val is not None else "--°"
            condition = self._service.weather_description or "Unknown"
            location = self._service.location or "Unknown"
            gradient_class = self._service.weather_gradient or "weather-clear"

            daily = self._service.daily_forecast
            if daily and len(daily) > 0:
                maxtemp = f"{round(float(daily[0].get('temperature_max', 0)))}°"
                mintemp = f"{round(float(daily[0].get('temperature_min', 0)))}°"
                maxmin = f"L:{mintemp} H:{maxtemp}"
            else:
                maxmin = "L:-- H:--"

            self.city.set_label(location)
            self.temperature.set_label(temp)
            self.condition_em.dynamic_file(f"weather/{icon_name}.svg")
            self.condition.set_label(condition)
            self.feels_like.set_label(maxmin)

            # Apply gradient class directly to the widget like other widgets do
            for cls in self.get_style_context().list_classes():
                if cls.startswith("weather-"):
                    self.remove_style_class(cls)
            self.add_style_class(gradient_class)

        except Exception as e:
            logger.error(f"[DesktopWeatherWidget] Error updating weather UI: {e}")
            self.city.set_label("Error")
            self.condition.set_label("UI Error")

    def destroy(self):
        try:
            self._service.disconnect_by_func(self._on_service_update)
        except ValueError as e:
            logger.warning(
                f"[widget] self._service.disconnect_by_func(self._on_service_update) failed: {e}"
            )
        super().destroy()


DesktopWidgetRegistry.register("weather", DesktopWeatherWidget, (174, 174))
