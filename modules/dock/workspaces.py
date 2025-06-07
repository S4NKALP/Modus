import json

from fabric.hyprland.service import Hyprland
from fabric.widgets.label import Label

connection = Hyprland()

def create_workspace_widget():
    workspaceData = connection.send_command("j/activeworkspace").reply
    activeWorkspace = json.loads(workspaceData.decode("utf-8"))["name"]
    workspace_label = Label(label=f"{activeWorkspace}")

    def on_workspace(obj, signal):
        nonlocal workspace_label
        activeWorkspace = json.loads(signal.data[0])
        workspace_label.set_label(f"{activeWorkspace}")

    connection.connect("event::workspace", on_workspace)
    return workspace_label
