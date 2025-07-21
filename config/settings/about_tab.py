from fabric.widgets.box import Box
from fabric.widgets.label import Label

from config.data import APP_NAME_CAP


class AboutTab:
    """About information tab for settings"""

    def __init__(self):
        pass

    def create_about_tab(self):
        """Create the About tab content"""
        vbox = Box(orientation="v", spacing=18, style="margin: 30px;")
        vbox.add(
            Label(
                markup=f"<b>{APP_NAME_CAP}</b>",
                h_align="start",
                style="font-size: 1.5em; margin-bottom: 8px;",
            )
        )
        vbox.add(
            Label(
                label="A hackable shell for Hyprland, powered by Fabric.",
                h_align="start",
                style="margin-bottom: 12px;",
            )
        )
        repo_box = Box(orientation="h", spacing=6, h_align="start")
        repo_label = Label(label="GitHub:", h_align="start")
        repo_link = Label(
            markup='<a href="https://github.com/S4NKALP/Modus">https://github.com/S4NKALP/Modus</a>'
        )
        repo_box.add(repo_label)
        repo_box.add(repo_link)
        vbox.add(repo_box)

        vbox.add(Box(v_expand=True))
        return vbox
