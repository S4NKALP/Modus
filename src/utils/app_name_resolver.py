import os
from collections import OrderedDict


class AppName:
    _MAX_CACHE = 128

    def __init__(self, path="/usr/share/applications"):
        self.files = os.listdir(path)
        self.path = path
        self._cache: OrderedDict[str, str | None] = OrderedDict()

    def get_app_name(self, wmclass, _format_=False):
        if wmclass in self._cache:
            self._cache.move_to_end(wmclass)
            return self._cache[wmclass]

        desktop_file = ""
        for f in self.files:
            if f.startswith(wmclass + ".desktop"):
                desktop_file = f
                break
        if desktop_file == "":
            for f in self.files:
                if f.lower().startswith(wmclass.lower() + ".desktop"):
                    desktop_file = f
                    break

        if desktop_file == "":
            result = None
        else:
            desktop_app_name = wmclass
            with open(os.path.join(self.path, desktop_file)) as f:
                lines = f.readlines()
                for line in lines:
                    if line.startswith("Name="):
                        desktop_app_name = line.split("=")[1].strip()
                        break
            result = desktop_app_name

        self._cache[wmclass] = result
        self._cache.move_to_end(wmclass)
        if len(self._cache) > self._MAX_CACHE:
            self._cache.popitem(last=False)
        return result

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
