from fabric.hyprland.widgets import HyprlandWorkspaces, WorkspaceButton
from fabric.utils import logger
from fabric.widgets.box import Box

from services.config import get_config, off_config_change, on_config_change
from utils.functions import is_special_workspace_id
from utils.gtk_utils import setup_cursor_hover

# TODO: Support multi-monitor setups


class WorkspaceIndicator(Box):
    def __init__(self, **kwargs):
        Box.__init__(
            self, name="workspace-indicator", orientation="h", spacing=4, **kwargs
        )
        self._current_config = {"hide_special_workspace": True}
        on_config_change(self._on_config_changed)

        self.workspaces = HyprlandWorkspaces(
            name="workspaces",
            spacing=4,
            buttons_factory=self._get_button_factory(),
        )

        self.add(self.workspaces)
        self.show_all()

        self._apply_initial_config()

    def _apply_initial_config(self):
        new_value = get_config("panel.hide_special_workspace", True)
        if new_value != self._current_config["hide_special_workspace"]:
            self._current_config["hide_special_workspace"] = new_value
            self.update_config({"hide_special_workspace": new_value})

    def _on_config_changed(self, new_config: dict, old_config: dict):
        new_panel = new_config.get("panel", {})
        old_panel = old_config.get("panel", {})
        new_val = new_panel.get("hide_special_workspace", True)
        old_val = old_panel.get("hide_special_workspace", True)
        if new_val != old_val:
            self._current_config["hide_special_workspace"] = new_val
            self.update_config({"hide_special_workspace": new_val})

    def _get_button_factory(self):
        if self._current_config.get("hide_special_workspace", True):
            return self._create_filtered_button
        else:
            return lambda ws_id: self._create_button_with_hover(ws_id)

    def _create_filtered_button(self, ws_id):
        if self._current_config.get(
            "hide_special_workspace", True
        ) and is_special_workspace_id(ws_id):
            return None
        return self._create_button_with_hover(ws_id)

    def _create_button_with_hover(self, ws_id):
        button = WorkspaceButton(id=ws_id, label=str(ws_id))
        setup_cursor_hover(button, "pointer")
        return button

    def update_config(self, new_config: dict):
        if "hide_special_workspace" in new_config:
            button_factory = self._get_button_factory()
            if hasattr(self, "workspaces") and self.workspaces:
                self.workspaces.destroy()

            self.workspaces = HyprlandWorkspaces(
                name="workspaces",
                spacing=4,
                buttons_factory=button_factory,
            )
            self.add(self.workspaces)
            self.workspaces.show_all()

    def destroy(self):
        try:
            off_config_change(self._on_config_changed)
        except Exception as e:
            logger.error(f"An error occurred: {e}")
        if hasattr(self, "workspaces") and self.workspaces:
            self.workspaces.destroy()
        Box.destroy(self)
