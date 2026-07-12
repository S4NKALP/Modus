import json

from fabric.hyprland.service import Hyprland
from fabric.widgets.label import Label
import config.data as data

connection = Hyprland()

workspaceData = connection.send_command("j/activeworkspace").reply
activeWorkspace = json.loads(workspaceData.decode("utf-8"))["name"]

# Create the workspace label with proper initialization
if not data.VERTICAL:
    workspace = Label(label=f"Workspace {activeWorkspace}", name="workspace-name")
else:
    workspace = Label(
        v_align="center",
        label="W\no\nr\nk\ns\np\na\nc\ne\n\n" + activeWorkspace,
        name="workspace-name",
    )


def on_workspace(obj, signal):
    global activeWorkspace
    activeWorkspace = json.loads(signal.data[0])
    if not data.VERTICAL:
        workspace.set_label(f"Workspace {activeWorkspace}")
    else:
        workspace.set_label(f"W\no\nr\nk\ns\np\na\nc\ne\n\n{activeWorkspace}")


connection.connect("event::workspace", on_workspace)
