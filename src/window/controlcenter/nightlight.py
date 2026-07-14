from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label

from services.modus import (
    is_night_light_active,
    toggle_night_light,
)
from utils.gtk_utils import svg_file


def create_night_light_widget(control_center):
    """Create night light widget for control center"""

    is_active = is_night_light_active()

    night_light_icon = svg_file(
        (
            "applets/redshift-status-on.svg"
            if is_active
            else "applets/redshift-status-off.svg"
        ),
        size=42,
    )

    night_light_status_label = Label(
        label="On" if is_active else "Off",
        name="nightlight-widget-label",
        style_classes="status-label",
        max_chars_width=15,
        ellipsization="end",
        h_align="start",
    )

    def toggle_ui(*_):
        if toggle_night_light():
            is_active = is_night_light_active()
            night_light_icon.dynamic_file(
                "applets/redshift-status-on.svg"
                if is_active
                else "applets/redshift-status-off.svg"
            )
            night_light_status_label.set_label("On" if is_active else "Off")

    night_light_widget = Box(
        name="nightlight-widget",
        orientation="h",
        h_expand=True,
        children=[
            Button(
                name="nightlight-icon-button",
                child=night_light_icon,
                on_clicked=toggle_ui,
            ),
            Button(
                name="nightlight-info-button",
                child=Box(
                    name="nightlight-widget-info",
                    h_expand=True,
                    v_expand=True,
                    v_align="center",
                    h_align="start",
                    orientation="vertical",
                    children=[
                        Label(
                            name="nightlight-widget-name",
                            label="Night Light",
                            style_classes="ct",
                            h_align="start",
                        ),
                        night_light_status_label,
                    ],
                ),
                on_clicked=toggle_ui,
            ),
        ],
    )

    return night_light_widget
