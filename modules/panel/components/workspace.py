from fabric.hyprland.widgets import HyprlandWorkspaces, WorkspaceButton
from fabric.widgets.box import Box

# TODO: Support Multi Monitor

class WorkspaceIndicator(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="workspace-indicator",
            orientation="h",
            spacing=4,
            **kwargs
        )
        
        self.workspaces = HyprlandWorkspaces(
            name="workspaces",
            spacing=4,
            buttons_factory=lambda ws_id: WorkspaceButton(
                id=ws_id, 
                label=str(ws_id)
            ),
        )
        
        self.add(self.workspaces)
        self.show_all()
