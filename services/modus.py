from typing import List

from loguru import logger

from fabric.core.service import Property, Service, Signal
from fabric.notifications import Notification
from services.custom_notification import CustomNotifications

notification_service = CustomNotifications()

class ModusService(Service):
    @Signal
    def bluetooth_changed(self, new_bluetooth: str) -> None: ...

    @Signal
    def volume_changed(self, new_volume: int) -> None: ...

    @Signal
    def wlan_changed(self, new_wlan: str) -> None: ...

    @Signal
    def battery_changed(self, new_battery: str) -> None: ...

    @Signal
    def dock_apps_changed(self, new_dock_apps: str) -> None: ...

    @Signal
    def dont_disturb_changed(self, value: bool) -> None: ...

    @Signal
    def current_active_app_name_changed(self, value: str) -> None: ...

    @Signal
    def music_changed(self, value: str) -> None: ...

    @Signal
    def current_dropdown_changed(self, value: str) -> None: ...

    @Signal
    def dropdowns_hide_changed(self, value: bool) -> None: ...

    @Signal
    def dock_width_changed(self, value: int) -> None: ...

    @Signal
    def dock_height_changed(self, value: int) -> None: ...

    @Signal
    def dock_hidden_changed(self, value: bool) -> None: ...

    @Signal
    def show_notificationcenter_changed(self, value: bool) -> None: ...

    @Signal
    def notification_count_changed(self, value: int) -> None: ...

    @Property(str, flags="read-write")
    def current_active_app_name(self) -> str:
        return self._current_active_app_name

    @Property(str, flags="read-write")
    def bluetooth(self) -> str:
        return self._bluetooth

    @Property(str, flags="read-write")
    def wlan(self) -> str:
        return self._wlan

    @Property(str, flags="read-write")
    def battery(self) -> str:
        return self._battery

    @Property(int, flags="read-write")
    def volume(self) -> int:
        return self._volume

    @Property(str, flags="read-write")
    def dock_apps(self) -> str:
        return self._dock_apps

    @Property(str, flags="read-write")
    def dont_disturb(self) -> bool:
        return self._dont_disturb

    @Property(str, flags="read-write")
    def music(self) -> str:
        return self._music

    @Property(str, flags="read-write")
    def current_dropdown(self) -> str:
        return self._current_dropdown

    @Property(bool, flags="read-write", default_value=False)
    def dropdowns_hide(self) -> bool:
        return self._dropdowns_hide

    @Property(int, flags="read-write")
    def dock_width(self) -> int:
        return self._dock_width

    @Property(int, flags="read-write")
    def dock_height(self) -> int:
        return self._dock_height

    @Property(bool, flags="read-write", default_value=False)
    def dock_hidden(self) -> bool:
        return self._dock_hidden

    @Property(bool, flags="read-write", default_value=False)
    def show_notificationcenter(self) -> bool:
        return self._show_notificationcenter

    @current_active_app_name.setter
    def current_active_app_name(self, value: str):
        if value != self._current_active_app_name:
            self._current_active_app_name = value
            self.current_active_app_name_changed(value)

    @volume.setter
    def volume(self, value: int):
        if value != self._volume:
            self._name = value
            self.volume_changed(value)

    @wlan.setter
    def wlan(self, value: str):
        if value != self._wlan:
            self._wlan = value
            self.wlan_changed(value)

    @battery.setter
    def battery(self, value: str):
        if value != self._battery:
            self._battery = value
            self.battery_changed(value)

    @bluetooth.setter
    def bluetooth(self, value: str):
        if value != self._bluetooth:
            self._bluetooth = value
            self.bluetooth_changed(value)

    @dock_apps.setter
    def dock_apps(self, value: str):
        if value != self._dock_apps:
            self._dock_apps = value
            self.dock_apps_changed(value)

    @dont_disturb.setter
    def dont_disturb(self, value: bool):
        if value != self._dont_disturb:
            self._dont_disturb = value
            self.dont_disturb_changed(value)

    @music.setter
    def music(self, value: str):
        if value != self._music:
            self._music = value
            self.music_changed(value)

    @current_dropdown.setter
    def current_dropdown(self, value: str):
        if value != self._current_dropdown:
            self._current_dropdown = value
            self.current_dropdown_changed(value)

    @dropdowns_hide.setter
    def dropdowns_hide(self, value: bool):
        if value != self._dropdowns_hide:
            self._dropdowns_hide = value
            self.dropdowns_hide_changed(value)

    @dock_width.setter
    def dock_width(self, value: int):
        if value != self._dock_width:
            self._dock_width = value
            self.dock_width_changed(value)

    @dock_height.setter
    def dock_height(self, value: int):
        if value != self._dock_height:
            self._dock_height = value
            self.dock_height_changed(value)

    @dock_hidden.setter
    def dock_hidden(self, value: bool):
        if value != self._dock_hidden:
            self._dock_hidden = value
            self.dock_hidden_changed(value)

    @show_notificationcenter.setter
    def show_notificationcenter(self, value: bool):
        if value != self._show_notificationcenter:
            self._show_notificationcenter = value
            self.show_notificationcenter_changed(value)

    def sc(self, signal_name: str, callback: callable, def_value="..."):
        self.connect(signal_name, callback)
        # Return current property value instead of default
        if signal_name == "bluetooth-changed":
            return self.bluetooth if self.bluetooth else "Off"
        elif signal_name == "wlan-changed":
            return self.wlan if self.wlan else "No Connection"
        elif signal_name == "battery-changed":
            return self.battery if self.battery else "Unknown"
        elif signal_name == "music-changed":
            return self.music if self.music else ""
        else:
            return def_value

    def __init__(self):
        super().__init__()
        self._volume = 0
        self._wlan = ""
        self._battery = ""
        self._bluetooth = ""
        self._dock_apps = ""
        self._dont_disturb = False
        self._current_active_app_name = ""
        self._music = ""
        self._current_dropdown = None
        self._dropdowns_hide = False
        self._dock_hidden = False
        self._show_notificationcenter = False

        self._dock_width = 0
        self._dock_height = 0


    def remove_notification(self, id: int):
        notification_service.remove_notification(id)
        self.notification_count_changed(self.notification_count)

    def cache_notification(self, data: Notification):
        widget_config = {"notification": {"per_app_limits": {}}}
        notification_service.cache_notification(widget_config, data, max_count=100)
        self.notification_count_changed(self.notification_count)

    def clear_all_notifications(self):
        notification_service.clear_all_notifications()
        self.notification_count_changed(self.notification_count)

    def get_deserialized(self) -> List[Notification]:
        return notification_service.get_deserialized()

    def get_deserialized_with_ids(self):
        return notification_service.get_deserialized_with_ids()

    @property
    def notification_count(self) -> int:
        return notification_service.count


global modus_service
try:
    modus_service = ModusService()
except Exception as e:
    logger.error("[Main] Failed to create EnvShellService:", e)
