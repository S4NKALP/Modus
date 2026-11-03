import json

from fabric.hyprland.widgets import HyprlandWorkspaces, WorkspaceButton
from fabric.utils import logger
from fabric.widgets.box import Box

from services.config import get_config, off_config_change, on_config_change
from utils.functions import is_special_workspace_id
from utils.gtk_utils import setup_cursor_hover

# TODO: Support multi-monitor setups

# Hyprland 0.57+ no longer includes an "id" for special workspaces, so we map
# their names to synthetic negative ids to keep Fabric's widget working.
_SPECIAL_WORKSPACE_ID_START = -100
_special_workspace_ids: dict[str, int] = {}
_special_workspace_names: dict[int, str] = {}


def _is_special_workspace_name(name: str | None) -> bool:
    return isinstance(name, str) and name.startswith("special:")


def _special_workspace_id(name: str) -> int:
    if name not in _special_workspace_ids:
        workspace_id = _SPECIAL_WORKSPACE_ID_START - len(_special_workspace_ids)
        _special_workspace_ids[name] = workspace_id
        _special_workspace_names[workspace_id] = name
    return _special_workspace_ids[name]


def get_special_workspace_name(workspace_id: int) -> str | None:
    return _special_workspace_names.get(workspace_id)


class CompatHyprlandWorkspaces(HyprlandWorkspaces):
    """HyprlandWorkspaces that tolerates special workspaces without an id."""

    def _event_workspace_id(self, data: list[str]) -> int | None:
        name = data[1] if len(data) > 1 else None
        if _is_special_workspace_name(name):
            return _special_workspace_id(name)
        try:
            return int(data[0])
        except (TypeError, ValueError):
            return None

    def on_ready(self):
        open_workspaces: list[dict] = json.loads(
            self.connection.send_command("j/workspaces").reply.decode()
        )
        active_workspace: dict = json.loads(
            self.connection.send_command("j/activeworkspace").reply.decode()
        )

        active_workspace_id = active_workspace.get("id")
        if active_workspace_id is None:
            active_name = active_workspace.get("name")
            if _is_special_workspace_name(active_name):
                active_workspace_id = _special_workspace_id(active_name)

        for workspace in open_workspaces:
            workspace_id = workspace.get("id")
            if workspace_id is None:
                name = workspace.get("name")
                if not _is_special_workspace_name(name):
                    logger.warning(
                        f"[Workspaces] Ignoring workspace without an id: {workspace}"
                    )
                    continue
                workspace_id = _special_workspace_id(name)

            self.workspace_created(workspace_id)
            if workspace_id == active_workspace_id:
                self.workspace_activated(workspace_id)

    def on_monitor(self, _, event):
        if len(event.data) != 2:
            return None
        name = event.data[1]
        if _is_special_workspace_name(name):
            return self.workspace_activated(_special_workspace_id(name))
        try:
            workspace_id = int(name)
        except (TypeError, ValueError):
            return None
        return self.workspace_activated(workspace_id)

    def on_workspace(self, _, event):
        if len(event.data) != 2:
            return None
        workspace_id = self._event_workspace_id(event.data)
        if workspace_id is None:
            return None
        return self.workspace_activated(workspace_id)

    def on_create_workspace(self, _, event):
        if len(event.data) != 2:
            return None
        workspace_id = self._event_workspace_id(event.data)
        if workspace_id is None:
            return None
        return self.workspace_created(workspace_id)

    def on_destroy_workspace(self, _, event):
        if len(event.data) != 2:
            return None
        workspace_id = self._event_workspace_id(event.data)
        if workspace_id is None:
            return None
        return self.workspace_destroyed(workspace_id)

    def on_urgent(self, _, event):
        if len(event.data) != 1:
            return None

        clients = json.loads(self.connection.send_command("j/clients").reply.decode())
        clients_map = {client["address"]: client for client in clients}
        urgent_client: dict = clients_map.get("0x" + event.data[0], {})
        raw_workspace = urgent_client.get("workspace")
        if not raw_workspace:
            return logger.warning(
                f"[Workspaces] received urgent signal, but data received ({event.data[0]}) is incorrect, skipping..."
            )

        name = raw_workspace.get("name")
        if _is_special_workspace_name(name):
            return self.urgent(_special_workspace_id(name))

        workspace_id = raw_workspace.get("id")
        if workspace_id is None:
            return logger.warning(
                f"[Workspaces] received urgent signal for a workspace without an id: {raw_workspace}"
            )
        return self.urgent(int(workspace_id))

    def do_button_clicked(self, button: WorkspaceButton):
        if name := get_special_workspace_name(button.id):
            return self.connection.send_command(
                self._focus_command_template.format(ws_id=name)
            )
        return super().do_button_clicked(button)


class WorkspaceIndicator(Box):
    def __init__(self, **kwargs):
        Box.__init__(
            self, name="workspace-indicator", orientation="h", spacing=4, **kwargs
        )
        self._current_config = {"hide_special_workspace": True}
        on_config_change(self._on_config_changed)

        self.workspaces = CompatHyprlandWorkspaces(
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
        label = get_special_workspace_name(ws_id)
        if label:
            label = label.removeprefix("special:")
        else:
            label = str(ws_id)
        button = WorkspaceButton(id=ws_id, label=label)
        setup_cursor_hover(button, "pointer")
        return button

    def update_config(self, new_config: dict):
        if "hide_special_workspace" in new_config:
            button_factory = self._get_button_factory()
            if hasattr(self, "workspaces") and self.workspaces:
                self.workspaces.destroy()

            self.workspaces = CompatHyprlandWorkspaces(
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
