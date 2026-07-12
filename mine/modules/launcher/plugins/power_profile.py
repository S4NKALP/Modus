from fabric.power_profiles import PowerProfiles
from fabric.utils import Gdk, idle_add, remove_handler
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label

from modules.launcher.base import LauncherPlugin


class PowerProfilePlugin(LauncherPlugin):
    @property
    def name(self) -> str:
        return "power_profile"

    @property
    def icon(self) -> str:
        return "power-profile-balanced"  # Default icon

    @property
    def keywords(self) -> list[str]:
        return ["power", "pp"]

    def __init__(self, handler):
        super().__init__(handler)
        self._query_handler: int = 0
        self.power_profiles = PowerProfiles()
        self.power_profiles.connect("changed", self._on_power_profile_changed)

        self.current_slots = []

    def on_search(self, text: str) -> None:
        self.query_power_profiles(text)

    def stop(self):
        if self._query_handler:
            remove_handler(self._query_handler)
        self._query_handler = 0

    def _on_power_profile_changed(self, *args):
        self._update_slot_statuses()

    def _update_slot_statuses(self) -> None:
        """Update the status indicators of all current slots"""
        for slot_info in self.current_slots:
            profile_name = slot_info["profile_name"]
            is_active = profile_name == self.power_profiles.active_profile
            display_name = profile_name.replace("-", " ").title()
            profile_text = f"{display_name} • Active" if is_active else display_name

            slot_info["label"].set_text(profile_text)
            if is_active:
                slot_info["label"].add_style_class("power-profile-active")
            else:
                slot_info["label"].remove_style_class("power-profile-active")

    def query_power_profiles(self, text: str) -> None:
        self.handler.start("power-profiles")
        self.current_slots = []
        self._current_search_text = text

        profiles = self.power_profiles.profiles
        if not profiles:
            self._show_no_profiles()
            return

        filtered_profiles = self._filter_profiles(text, profiles)
        if not filtered_profiles:
            return

        self._query_handler = idle_add(
            self._bake_next_profile_slot, iter(filtered_profiles), pin=True
        )

    def _filter_profiles(self, text: str, profiles) -> list:
        return (
            profiles
            if not text.strip()
            else [
                profile for profile in profiles if text.lower() in str(profile).lower()
            ]
        )

    def _show_no_profiles(self) -> None:
        self.handler.slot_ready(
            Button(
                style_classes="app-slot power-profile-no-profiles",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Image(icon_name="power-profile-balanced", size=32),
                        Label(
                            label="No power profiles available",
                            style_classes="power-profile-no-profiles-text",
                            h_align="center",
                        ),
                    ],
                ),
                tooltip_text="No power profiles are available on this system",
            ),
            "power-profiles",
        )
        self.handler.done()

    def _bake_next_profile_slot(self, iterator) -> bool:
        profile = next(iterator, None)
        if profile is None:
            idle_add(self.handler.done)
            return False
        self._create_profile_slot(profile)
        return True

    def _create_profile_slot(self, profile) -> None:
        profile_name = (
            profile.get("Profile", str(profile))
            if isinstance(profile, dict)
            else str(profile)
        )

        is_active = profile_name == self.power_profiles.active_profile
        icon_name = f"power-profile-{profile_name}"
        display_name = profile_name.replace("-", " ").title()
        profile_text = f"{display_name} • Active" if is_active else display_name

        label_widget = Label(
            label=profile_text,
            style_classes=f"power-profile-name {'power-profile-active' if is_active else ''}",
            h_align="start",
            v_align="center",
        )

        slot_content = Box(
            orientation="h",
            spacing=12,
            children=[
                Image(icon_name=icon_name, h_align="start", size=32),
                label_widget,
            ],
        )

        slot_widget = Button(
            style_classes="app-slot power-profile-slot",
            child=slot_content,
            tooltip_text=f"Click to set power profile to {display_name}\nCurrent: {self.power_profiles.active_profile}",
            on_clicked=lambda *_: self._set_power_profile(profile_name),
        )

        slot_widget.connect(
            "key-press-event",
            lambda widget, event, p=profile_name: self._on_slot_key_press(
                widget, event, p
            ),
        )

        self.current_slots.append(
            {
                "profile_name": profile_name,
                "label": label_widget,
            }
        )
        self.handler.slot_ready(slot_widget, "power-profiles")

    def _set_power_profile(self, profile: str) -> None:
        if profile != self.power_profiles.active_profile:
            self.power_profiles.active_profile = profile

    def _on_slot_key_press(self, widget, event, profile: str) -> bool:
        if not event or event.keyval not in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            return False
        self._set_power_profile(profile)
        return True

    def handle_external(self, command: str, args: str) -> None:
        if args:
            self._set_power_profile(args)
