import json

from fabric.hyprland.service import Hyprland
from fabric.widgets.label import Label

connection = Hyprland()

workspaceData = connection.send_command("j/activeworkspace").reply
activeWorkspace = json.loads(workspaceData.decode("utf-8"))["name"]
workspace = Label(
    v_align="center",
    label="W\no\nr\nk\ns\np\na\nc\ne\n\n" + activeWorkspace,
    name="workspace-name",
)


def on_workspace(obj, signal):
    global activeWorkspace
    activeWorkspace = json.loads(signal.data[0])
    workspace.set_label(f"W\no\nr\nk\ns\np\na\nc\ne\n\n{activeWorkspace}")


connection.connect("event::workspace", on_workspace)
