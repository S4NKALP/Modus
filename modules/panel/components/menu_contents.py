"""
Menu contents definitions for the macOS-style menu bar.
This file contains all the menu items and their organization.
"""


def get_default_menu_contents():
    return {
        "Hyprland": [],
        "File": [],
        "Edit": [],
        "View": ["Full Screen", "---", "Zoom In", "Zoom Out", "Actual Size"],
        "Go": [
            "Back",
            "Forward",
        ],
        "Window": [
            "Move Window to Left",
            "Move Window to Right",
            "Cycle Through Windows",
            "---",
            "Float",
            "Pseudo",
            "Center",
            "Group",
            "Pin",
            "Quit",
        ],
        "Help": [
            "---",
            "Hyprland Help",
            "Arch Wiki",
            "Keyboard Shortcuts",
            "---",
            "Report a Bug...",
        ],
    }


def get_app_menu_template():
    return ["About {app_name}", "---", "Hide {app_name}", "---", "Quit {app_name}"]


def create_app_menu(app_name):
    template = get_app_menu_template()
    return [
        item.format(app_name=app_name) if "{app_name}" in item else item
        for item in template
    ]


def get_menu_contents_for_app(app_name):
    contents = get_default_menu_contents().copy()

    if app_name and app_name != "Hyprland":
        # Replace the Hyprland menu with app-specific menu
        contents["Hyprland"] = create_app_menu(app_name)

    return contents


def get_app_specific_menu_contents(app_name):
    return get_menu_contents_for_app(app_name)
