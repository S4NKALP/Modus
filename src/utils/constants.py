from tomlkit import document as _document
from tomlkit import dumps as _dumps
from tomlkit import table as _table

DEFAULT = {
    "general": {
        "debug": False,
        "wallpapers_dir": "src/assets/wallpaper_example/",
        "keyboard_layouts": ["us"],
        "weather_location": "",
    },
    "dock": {
        "enabled": True,
        "position": "bottom",
        "auto_hide": True,
        "always_occluded": False,
        "icon_size": 52,
        "hide_special_workspace_apps": True,
        "hover_scale": 1.6,
    },
    "panel": {
        "imac_button": True,
        "systray": True,
        "systray_ignore": ["blueman", "network"],
        "control_center": True,
        "search": True,
        "global_menu": True,
        "network": True,
        "battery": True,
        "notification_center": True,
        "workspace_indicator": True,
        "bluetooth": True,
        "date_time": True,
        "night_light_temperature": 4500,
        "notch": True,
        "osd": True,
        "hide_special_workspace": True,
        "custom_mods": True,
    },
    "switcher": {
        "live_preview": True,
        "live_preview_delay_ms": 200,
        "window_switcher": True,
    },
    "notification": {
        "timeout": "5s",
        "ignored_apps": ["Hyprshot"],
        "limited_apps_history": ["Spotify"],
    },
}


def generate_default_toml() -> str:
    """Build default config.toml with inline comments."""
    doc = _document()

    general = _table()
    general.add("debug", False)
    general.add("wallpapers_dir", "src/assets/wallpaper_example/")
    general.add("keyboard_layouts", ["us"])
    general.add("weather_location", "")
    doc.add("general", general)

    dock = _table()
    dock.add("enabled", True)
    dock.add("position", "bottom")
    dock["position"].comment("'bottom' | 'left' | 'right'")
    dock.add("auto_hide", True)
    dock.add("always_occluded", False)
    dock.add("icon_size", 52)
    dock.add("hide_special_workspace_apps", True)
    dock.add("hover_scale", 1.6)
    dock["hover_scale"].comment(
        "1.0 (min, no effect) to 2.0 (max) | >2.0 not recommended — icons get blurry/pixelated on hover"
    )
    doc.add("dock", dock)

    panel = _table()
    panel.add("imac_button", True)
    panel.add("systray", True)
    panel.add("systray_ignore", ["blueman", "network"])
    panel.add("control_center", True)
    panel.add("search", True)
    panel.add("global_menu", True)
    panel.add("network", True)
    panel.add("battery", True)
    panel.add("notification_center", True)
    panel.add("workspace_indicator", True)
    panel.add("bluetooth", True)
    panel.add("date_time", True)
    panel.add("night_light_temperature", 4500)
    panel.add("notch", True)
    panel.add("osd", True)
    panel.add("hide_special_workspace", True)
    panel.add("custom_mods", True)
    doc.add("panel", panel)

    switcher = _table()
    switcher.add("live_preview", True)
    switcher.add("live_preview_delay_ms", 200)
    switcher.add("window_switcher", True)
    doc.add("switcher", switcher)

    notification = _table()
    notification.add("timeout", "5s")
    notification.add("ignored_apps", ["Hyprshot"])
    notification.add("limited_apps_history", ["Spotify"])
    doc.add("notification", notification)

    return _dumps(doc)
