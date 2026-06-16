from fabric.hyprland.widgets import HyprlandWorkspaces, WorkspaceButton
from fabric.widgets.box import Box

from services.config import get_config, on_config_change
from utils.functions import is_special_workspace_id
from utils.utils import setup_cursor_hover

# TODO: Support multi-monitor setups


class LuaHyprlandWorkspaces(HyprlandWorkspaces):
    def do_action_next(self):
        ws = "e" if not self._empty_scroll else ""
        return self.connection.send_command(
            f"batch/dispatch hl.dsp.focus({{workspace=[[{ws}+1]]}})"
        )

    def do_action_previous(self):
        ws = "e" if not self._empty_scroll else ""
        return self.connection.send_command(
            f"batch/dispatch hl.dsp.focus({{workspace=[[{ws}-1]]}})"
        )

    def do_button_clicked(self, button: WorkspaceButton):
        return self.connection.send_command(
            f"batch/dispatch hl.dsp.focus({{workspace=[[{button.id}]]}})"
        )


class WorkspaceIndicator(Box):
    def __init__(self, **kwargs):
        Box.__init__(
            self, name="workspace-indicator", orientation="h", spacing=4, **kwargs
        )
        self._current_config = {"hide_special_workspace": True}
        on_config_change(self._on_config_changed)

        self.workspaces = LuaHyprlandWorkspaces(
            name="workspaces",
            spacing=4,
            buttons_factory=self._get_button_factory(),
        )

        self.add(self.workspaces)
        self.show_all()

        self._apply_initial_config()

    def _apply_initial_config(self):
        new_value = get_config("hide_special_workspace", True)
        if new_value != self._current_config["hide_special_workspace"]:
            self._current_config["hide_special_workspace"] = new_value
            self.update_config({"hide_special_workspace": new_value})

    def _on_config_changed(self, new_config: dict, old_config: dict):
        if "hide_special_workspace" in new_config and new_config.get(
            "hide_special_workspace"
        ) != old_config.get("hide_special_workspace"):
            self._current_config["hide_special_workspace"] = new_config.get(
                "hide_special_workspace", True
            )
            self.update_config(
                {
                    "hide_special_workspace": self._current_config[
                        "hide_special_workspace"
                    ]
                }
            )

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

            self.workspaces = LuaHyprlandWorkspaces(
                name="workspaces",
                spacing=4,
                buttons_factory=button_factory,
            )
            self.add(self.workspaces)
            self.workspaces.show_all()

    def destroy(self):
        try:
            from services.config import _config_handlers

            if self._on_config_changed in _config_handlers:
                _config_handlers.remove(self._on_config_changed)
        except Exception:
            pass
        if hasattr(self, "workspaces") and self.workspaces:
            self.workspaces.destroy()
        Box.destroy(self)
