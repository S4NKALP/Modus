from fabric.hyprland.widgets import HyprlandWorkspaces, WorkspaceButton
from fabric.widgets.box import Box
import config.data as data
from utils.functions import is_special_workspace_id

# TODO: Support Multi Monitor


class WorkspaceIndicator(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="workspace-indicator", orientation="h", spacing=4, **kwargs
        )

        # Create workspace widget with custom button factory if filtering is enabled
        if data.HIDE_SPECIAL_WORKSPACE:
            self.workspaces = HyprlandWorkspaces(
                name="workspaces",
                spacing=4,
                buttons_factory=self._create_filtered_button,
            )
        else:
            self.workspaces = HyprlandWorkspaces(
                name="workspaces",
                spacing=4,
                buttons_factory=lambda ws_id: WorkspaceButton(
                    id=ws_id, label=str(ws_id)
                ),
            )

        self.add(self.workspaces)
        self.show_all()

    def _is_special_workspace_id(self, ws_id):
        return is_special_workspace_id(ws_id)

    def _create_filtered_button(self, ws_id):
        if data.HIDE_SPECIAL_WORKSPACE and self._is_special_workspace_id(ws_id):
            # Return None or an empty widget to hide special workspaces
            return None

        return WorkspaceButton(id=ws_id, label=str(ws_id))


