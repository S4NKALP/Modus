from fabric import Fabricator
from fabric.utils import exec_shell_command
from fabric.widgets.box import Box
from snippets import MaterialIcon

PROFILE_ICONS = {
    "power-saver": "data_saver_on",
    "balanced": None,
    "performance": "mode_heat",
}


class PowerProfileIndicator(Box):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.profile_icon = None

        self.fabricator = Fabricator(interval=1000, poll_from=self.update_power_profile)

    def update_power_profile(self, *_):
        profile = self.get_power_profile()
        self.update_icon(profile)
        return True

    def get_power_profile(self):
        result = exec_shell_command("powerprofilesctl get")
        return result.strip() or "power-saver"

    def update_icon(self, profile):
        icon_name = PROFILE_ICONS.get(profile)

        new_icon = MaterialIcon(icon_name, 16) if icon_name else None

        if self.profile_icon:
            self.remove(self.profile_icon)

        if new_icon:
            self.profile_icon = new_icon
            self.add(self.profile_icon)
        else:
            if self.profile_icon:
                self.profile_icon.hide()
                self.profile_icon = None
