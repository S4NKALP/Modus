# type: ignore
from fabric.core.service import Service, Signal, Property
from fabric.notifications import Notification
from typing import List


class ModusService(Service):
    @Signal
    def notification_count_changed(self, value: int) -> None: ...
    @Signal
    def dont_disturb_changed(self, value: bool) -> None: ...
    @Signal
    def show_notificationcenter_changed(self, value: bool) -> None: ...
    @Property(bool, flags="read-write", default_value=False)
    def show_notificationcenter(self) -> bool:
        return self._show_notificationcenter

    @Property(str, flags="read-write")
    def notification_count(self) -> int:
        return self._notification_count

    @Property(str, flags="read-write")
    def dont_disturb(self) -> bool:
        return self._dont_disturb

    @dont_disturb.setter
    def dont_disturb(self, value: bool):
        if value != self._dont_disturb:
            self._dont_disturb = value
            self.dont_disturb_changed(value)

    @show_notificationcenter.setter
    def show_notificationcenter(self, value: bool):
        if value != self._show_notificationcenter:
            self._show_notificationcenter = value
            self.show_notificationcenter_changed(value)

    def sc(self, signal_name: str, callback: callable, def_value="..."):
        self.connect(signal_name, callback)
        return def_value

    def __init__(self):
        super().__init__()
        self._notifications = []
        self._notification_count = len(self._notifications)
        self._dont_disturb = False
        self._show_notificationcenter = False

        self.notifications = []

    def remove_notification(self, id: int):
        item = next((p for p in self._notifications if p["id"] == id), None)
        if item is None:
            return
        index = self._notifications.index(item)

        self._notifications.pop(index)
        self._notification_count -= 1
        self.notification_count_changed(self._notification_count)
        if self._notification_count == 0:
            self.clear_all_changed(True)

    def cache_notification(self, data: Notification):
        existing_data = self._notifications
        serialized_data = data.serialize()
        serialized_data.update({"id": self._notification_count + 1})
        existing_data.append(serialized_data)

        self._notification_count += 1
        self._notifications = existing_data
        self.notification_count_changed(self._notification_count)

    def clear_all_notifications(self):
        self._notifications = []
        self._notification_count = 0

        self.clear_all_changed(True)
        self.notification_count_changed(self._notification_count)

    def get_deserialized(self) -> List[Notification]:
        if len(self.notifications) <= 0:
            self.notifications = [
                Notification.deserialize(data) for data in self._notifications
            ]
        return self.notifications
