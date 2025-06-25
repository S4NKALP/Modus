import json
import subprocess

import config.data as data
from fabric.hyprland.service import Hyprland
from fabric.hyprland.widgets import WorkspaceButton, Workspaces
from fabric.widgets.box import Box
from fabric.widgets.button import Button

CHINESE_NUMERALS = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "〇"]


class Workspace(Button):
    def __init__(self):
        should_invert = data.DOCK_THEME in ["Dense", "Edge"] or (
            data.DOCK_THEME == "Pills" and data.DOCK_POSITION in ["Left", "Right"]
        )

        super().__init__(
            name="workspace-single",
            can_focus=True,
            receives_default=True,
            relief="none",
            style_classes="invert" if should_invert else None,
        )

        self.connection = Hyprland()
        self.activeWorkspace = str(self._get_active_workspace())

        self.set_label(str(self.activeWorkspace))
        self.connect("clicked", self._on_click)
        self.connection.connect("event::workspace", self._on_workspace_changed)

        self.set_sensitive(True)
        self.show_all()

    def _get_active_workspace(self):
        active = self.connection.send_command("j/activeworkspace").reply
        return json.loads(active.decode("utf-8"))["name"]

    def _get_active_workspaces(self):
        clients_data = self.connection.send_command("j/clients").reply
        clients = json.loads(clients_data.decode("utf-8"))

        active_workspaces = set()
        for client in clients:
            if "workspace" in client and "name" in client["workspace"]:
                workspace_name = str(client["workspace"]["name"])
                active_workspaces.add(workspace_name)

        return sorted(
            list(active_workspaces), key=lambda x: int(x) if x.isdigit() else x
        )

    def _on_click(self, _widget):
        self._cycle_workspace()

    def _cycle_workspace(self):
        active_workspaces = self._get_active_workspaces()

        if not active_workspaces:
            return

        if str(self.activeWorkspace) not in active_workspaces:
            active_workspaces.append(str(self.activeWorkspace))
            active_workspaces.sort(key=lambda x: int(x) if x.isdigit() else x)

        current_index = active_workspaces.index(self.activeWorkspace)
        next_index = (current_index + 1) % len(active_workspaces)
        next_workspace = active_workspaces[next_index]

        cmd = ["hyprctl", "dispatch", "workspace", str(next_workspace)]
        subprocess.run(cmd, capture_output=True, text=True, timeout=2)

        self.activeWorkspace = str(next_workspace)
        self.set_label(str(self.activeWorkspace))

    def _on_workspace_changed(self, _obj, signal):
        """Handle workspace change events from Hyprland"""
        workspace_data = json.loads(signal.data[0])
        self.activeWorkspace = str(workspace_data)
        self.set_label(str(self.activeWorkspace))


workspaces = Workspaces(
    name="workspaces",
    invert_scroll=True,
    empty_scroll=True,
    v_align="fill",
    orientation="h" if not data.VERTICAL else "v",
    spacing=8,
    buttons=[
        WorkspaceButton(
            h_expand=False,
            v_expand=False,
            h_align="center",
            v_align="center",
            id=i,
            label=None,
            style_classes=["vertical"] if data.VERTICAL else None,
        )
        for i in range(1, 11)
    ],
    buttons_factory=None
            if data.DOCK_HIDE_SPECIAL_WORKSPACE
            else Workspaces.default_buttons_factory,
)

workspaces_num = Workspaces(
    name="workspaces-num",
    invert_scroll=True,
    empty_scroll=True,
    v_align="fill",
    orientation="h" if not data.VERTICAL else "v",
    spacing=0 if not data.WORKSPACE_USE_CHINESE_NUMERAL else 4,
    buttons=[
        WorkspaceButton(
            h_expand=False,
            v_expand=False,
            h_align="center",
            v_align="center",
            id=i,
            label=CHINESE_NUMERALS[i - 1]
            if data.WORKSPACE_USE_CHINESE_NUMERAL and 1 <= i <= len(CHINESE_NUMERALS)
            else str(i),
        )
        for i in range(1, 11)
    ],
    buttons_factory=None
            if data.DOCK_HIDE_SPECIAL_WORKSPACE
            else Workspaces.default_buttons_factory,
)


workspaceactive = Workspace()

workspace = Box(
    name="workspaces-container",
    children=[
        workspaces
        if data.WORKSPACE_DOTS
        else workspaces_num
        if data.WORKSPACE_NUMS
        else workspaceactive
    ],
)
