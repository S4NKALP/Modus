import os


class AppName:
    def __init__(self, path="/usr/share/applications"):
        self.files = os.listdir(path)
        self.path = path
        self._cache: dict[str, str | None] = {}

    def get_app_name(self, wmclass, _format_=False):
        if wmclass in self._cache:
            return self._cache[wmclass]

        desktop_file = ""
        for f in self.files:
            if f.startswith(wmclass + ".desktop"):
                desktop_file = f

        if desktop_file == "":
            self._cache[wmclass] = None
            return None

        desktop_app_name = wmclass
        with open(os.path.join(self.path, desktop_file)) as f:
            lines = f.readlines()
            for line in lines:
                if line.startswith("Name="):
                    desktop_app_name = line.split("=")[1].strip()
                    break
        self._cache[wmclass] = desktop_app_name
        return desktop_app_name

    def format_app_name(self, title, wmclass, update=False):
        # Handle case when both title and wmclass are empty (no active window)
        if not title and not wmclass:
            name = "Modus"
        else:
            name = wmclass
            if name == "":
                name = title

            # Try to get the proper app name from desktop file only if wmclass is not empty
            if wmclass:
                resolved = self.get_app_name(wmclass=wmclass)
                if resolved is not None:
                    name = resolved
                elif title:
                    name = title

            # Smart title formatting (capitalize first letter)
            name = str(name).title()
            if "." in name:
                name = name.split(".")[-1]

        if update:
            from utils.roam import modus_service

            modus_service.current_active_wm_class = wmclass
            modus_service.current_active_app_name = name
        return name


# Create a global instance for use across modules
app_name_resolver = AppName()


def format_window(title, wmclass):
    # Clean up "unknown" values to ensure they are treated as empty
    if title == "unknown":
        title = ""
    if wmclass == "unknown":
        wmclass = ""

    # Always call format_app_name with update=True to keep service state in sync
    return app_name_resolver.format_app_name(title, wmclass, True)
