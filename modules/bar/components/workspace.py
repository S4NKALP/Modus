import json

from fabric.hyprland.service import Hyprland
from fabric.widgets.label import Label

connection = Hyprland()

workspaceData = connection.send_command("j/activeworkspace").reply
activeWorkspace = json.loads(workspaceData.decode("utf-8"))["name"]
workspace = Label(label=f"Workspace {activeWorkspace}")


def on_workspace(obj, signal):
    global activeWorkspace
    activeWorkspace = json.loads(signal.data[0])
    workspace.set_label(f"Workspace {activeWorkspace}")


connection.connect("event::workspace", on_workspace)
