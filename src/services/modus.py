import json
import os
import sys

from fabric.core.service import Property, Service, Signal
from fabric.hyprland.service import Hyprland
from fabric.utils import exec_shell_command_async, logger

from services.custom_notification import CachedNotifications
from services.inhibit import get_inhibit_service
from utils.app_name_resolver import app_name_resolver
from utils.functions import (
    find_binary,
    find_process_pid,
    spawn_detached,
)
from utils.functions import (
    kill_process as _kill_process,
)


def __getattr__(name):
    mod = sys.modules[__name__]
    if name == "notification_service":
        _inst = CachedNotifications()
        setattr(mod, name, _inst)
        return _inst
    if name == "modus_service":
        return get_modus_service()
    if name == "audio_service":
        try:
            from fabric.audio import Audio

            _inst = Audio()
        except Exception as e:
            logger.error(f"[Main] Failed to create AudioService: {e}")
            _inst = None
        setattr(mod, name, _inst)
        return _inst
    if name == "screen_capture_service":
        from services.screencapture import ScreenCapture

        _inst = ScreenCapture()
        setattr(mod, name, _inst)
        return _inst
    if name == "screenshot_service":
        from services.screenshot import Screenshot

        _inst = Screenshot()
        setattr(mod, name, _inst)
        return _inst
    if name == "screen_recorder_service":
        from services.screenrecorder import ScreenRecorder

        _inst = ScreenRecorder()
        setattr(mod, name, _inst)
        return _inst
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def get_notification_service():
    import sys

    return sys.modules[__name__].notification_service


class ModusService(Service):
    @Signal
    def bluetooth_changed(self, new_bluetooth: str) -> None: ...

    @Signal
    def volume_changed(self, new_volume: int) -> None: ...

    @Signal
    def wlan_changed(self, new_wlan: str) -> None: ...

    @Signal
    def battery_changed(self, new_battery: str) -> None: ...

    @Signal
    def dont_disturb_changed(self, value: bool) -> None: ...

    @Signal
    def current_active_app_name_changed(self, value: str) -> None: ...

    @Signal
    def current_active_wm_class_changed(self, value: str) -> None: ...

    @Signal
    def current_workspace_changed(self, value: str) -> None: ...

    @Signal
    def music_changed(self, value: str) -> None: ...

    @Signal
    def current_dropdown_changed(self, value: str) -> None: ...

    @Signal
    def dropdowns_hide_changed(self, value: bool) -> None: ...

    @Signal
    def dock_width_changed(self, value: int) -> None: ...

    @Signal
    def dock_height_changed(self, value: int) -> None: ...

    @Signal
    def dock_hidden_changed(self, value: bool) -> None: ...

    @Signal
    def show_notificationcenter_changed(self, value: bool) -> None: ...

    @Signal
    def fullscreen_changed(self, value: bool) -> None: ...

    @Signal
    def notification_count_changed(self, value: int) -> None: ...

    @Property(str, flags="read-write")
    def current_active_app_name(self) -> str:
        return self._current_active_app_name

    @Property(str, flags="read-write")
    def current_active_wm_class(self) -> str:
        return self._current_active_wm_class

    @Property(str, flags="read-write")
    def current_workspace(self) -> str:
        return self._current_workspace

    @Property(str, flags="read-write")
    def bluetooth(self) -> str:
        return self._bluetooth

    @Property(str, flags="read-write")
    def wlan(self) -> str:
        return self._wlan

    @Property(str, flags="read-write")
    def battery(self) -> str:
        return self._battery

    @Property(int, flags="read-write")
    def volume(self) -> int:
        return self._volume

    @Property(str, flags="read-write")
    def dock_apps(self) -> str:
        return self._dock_apps

    @Property(bool, flags="read-write", default_value=False)
    def dont_disturb(self) -> bool:
        return self._dont_disturb

    @Property(str, flags="read-write")
    def music(self) -> str:
        return self._music

    @Property(str, flags="read-write")
    def current_dropdown(self) -> str:
        return self._current_dropdown

    @Property(bool, flags="read-write", default_value=False)
    def dropdowns_hide(self) -> bool:
        return self._dropdowns_hide

    @Property(int, flags="read-write")
    def dock_width(self) -> int:
        return self._dock_width

    @Property(int, flags="read-write")
    def dock_height(self) -> int:
        return self._dock_height

    @Property(bool, flags="read-write", default_value=False)
    def dock_hidden(self) -> bool:
        return self._dock_hidden

    @Property(bool, flags="read-write", default_value=False)
    def show_notificationcenter(self) -> bool:
        return self._show_notificationcenter

    @Property(bool, flags="read-write", default_value=False)
    def fullscreen(self) -> bool:
        return self._fullscreen

    @fullscreen.setter
    def fullscreen(self, value: bool):
        if value != self._fullscreen:
            self._fullscreen = value
            self.fullscreen_changed(value)

    @current_active_app_name.setter
    def current_active_app_name(self, value: str):
        if value != self._current_active_app_name:
            self._current_active_app_name = value
            self.current_active_app_name_changed(value)

    @current_active_wm_class.setter
    def current_active_wm_class(self, value: str):
        if value != self._current_active_wm_class:
            self._current_active_wm_class = value
            self.current_active_wm_class_changed(value)

    @current_workspace.setter
    def current_workspace(self, value: str):
        if value != self._current_workspace:
            self._current_workspace = value
            self.current_workspace_changed(value)

    @volume.setter
    def volume(self, value: int):
        if value != self._volume:
            self._volume = value
            self.volume_changed(value)

    @wlan.setter
    def wlan(self, value: str):
        if value != self._wlan:
            self._wlan = value
            self.wlan_changed(value)

    @battery.setter
    def battery(self, value: str):
        if value != self._battery:
            self._battery = value
            self.battery_changed(value)

    @bluetooth.setter
    def bluetooth(self, value: str):
        if value != self._bluetooth:
            self._bluetooth = value
            self.bluetooth_changed(value)

    @dont_disturb.setter
    def dont_disturb(self, value: bool):
        if value != self._dont_disturb:
            self._dont_disturb = value
            self.dont_disturb_changed(value)

    @music.setter
    def music(self, value: str):
        if value != self._music:
            self._music = value
            self.music_changed(value)

    @current_dropdown.setter
    def current_dropdown(self, value: str):
        if value != self._current_dropdown:
            self._current_dropdown = value
            self.current_dropdown_changed(value)

    @dropdowns_hide.setter
    def dropdowns_hide(self, value: bool):
        if value != self._dropdowns_hide:
            self._dropdowns_hide = value
            self.dropdowns_hide_changed(value)

    @dock_width.setter
    def dock_width(self, value: int):
        if value != self._dock_width:
            self._dock_width = value
            self.dock_width_changed(value)

    @dock_height.setter
    def dock_height(self, value: int):
        if value != self._dock_height:
            self._dock_height = value
            self.dock_height_changed(value)

    @dock_hidden.setter
    def dock_hidden(self, value: bool):
        if value != self._dock_hidden:
            self._dock_hidden = value
            self.dock_hidden_changed(value)

    @show_notificationcenter.setter
    def show_notificationcenter(self, value: bool):
        if value != self._show_notificationcenter:
            self._show_notificationcenter = value
            self.show_notificationcenter_changed(value)

    def sc(self, signal_name: str, callback: callable, def_value="..."):
        self.connect(signal_name, callback)
        if signal_name == "bluetooth-changed":
            return self.bluetooth if self.bluetooth else "Off"
        elif signal_name == "wlan-changed":
            return self.wlan if self.wlan else "No Connection"
        elif signal_name == "battery-changed":
            return self.battery if self.battery else "Unknown"
        elif signal_name == "music-changed":
            return self.music if self.music else ""
        else:
            return def_value

    def __init__(self):
        super().__init__()
        self._volume = 0
        self._wlan = ""
        self._battery = ""
        self._bluetooth = ""
        self._dock_apps = ""
        self._dont_disturb = False
        self._current_active_app_name = "Finder"
        self._current_active_wm_class = ""
        self._current_workspace = "1"
        self._music = ""
        self._current_dropdown = None
        self._dropdowns_hide = False
        self._dock_hidden = False
        self._show_notificationcenter = False
        self._dock_width = 0
        self._dock_height = 0
        self._fullscreen = False

    @property
    def notification_count(self) -> int:
        return get_notification_service().count


_modus_instance: ModusService | None = None
_hyprland_connection: Hyprland | None = None


def get_modus_service() -> ModusService:
    global _modus_instance
    if _modus_instance is None:
        try:
            _modus_instance = ModusService()
            _setup_workspace_monitoring()
            _setup_active_window_monitoring()
        except Exception as e:
            logger.error("[ModusService] Failed to create instance:", e)
            raise
    return _modus_instance


def _setup_workspace_monitoring():
    global _hyprland_connection
    service = get_modus_service()
    try:
        _hyprland_connection = Hyprland()
        service._hyprland_connection = _hyprland_connection
        workspace_data = _hyprland_connection.send_command("j/activeworkspace").reply
        active_workspace = json.loads(workspace_data.decode("utf-8"))["name"]
        service._current_workspace = str(active_workspace)
        _hyprland_connection.connect("event::workspace", _on_workspace_changed)
        _hyprland_connection.connect("event::fullscreen", _on_fullscreen_changed)
    except Exception as e:
        logger.error(f"[ModusService] Failed to setup workspace monitoring: {e}")
        service._current_workspace = "1"


def _setup_active_window_monitoring():
    global _hyprland_connection
    get_modus_service()
    try:
        if not _hyprland_connection:
            return
        _update_active_window()
    except Exception as e:
        logger.error(f"[ModusService] Failed to setup active window monitoring: {e}")


def _update_active_window():
    global _hyprland_connection
    service = get_modus_service()
    try:
        if not _hyprland_connection:
            return
        window_data = _hyprland_connection.send_command("j/activewindow").reply
        if not window_data:
            service.current_active_app_name = "Finder"
            return
        window_info = json.loads(window_data.decode("utf-8"))
        wmclass = window_info.get("class", "")
        title = window_info.get("title", "")
        if not title and not wmclass:
            service.current_active_app_name = "Finder"
            return

        name = app_name_resolver.format_app_name(title, wmclass)
        service.current_active_wm_class = wmclass
        service.current_active_app_name = name
    except Exception as e:
        logger.error(f"[ModusService] Error updating active window: {e}")
        service.current_active_app_name = "Finder"


def _on_workspace_changed(obj, signal):
    service = get_modus_service()
    try:
        workspace_name = json.loads(signal.data[0])
        service.current_workspace = str(workspace_name)
    except Exception as e:
        logger.error(f"[ModusService] Error processing workspace change: {e}")


def _on_fullscreen_changed(obj, event):
    service = get_modus_service()
    try:
        data = event.data[0] if event.data else ""
        mode = data.split(":")[-1] if ":" in data else "0"
        service.fullscreen = mode in ("1", "2")
    except Exception as e:
        logger.error(f"[ModusService] Error processing fullscreen change: {e}")


def toggle_dnd():
    ns = get_notification_service()
    ns.toggle_dnd()
    get_modus_service().dont_disturb_changed(ns.dont_disturb)


# --- Night light orchestration ---
_night_light_active = False


def toggle_night_light() -> bool:
    global _night_light_active
    try:
        if _night_light_active:
            _kill_process("hyprsunset")
            _night_light_active = False
        else:
            spawn_detached(["hyprsunset", "-t", "4500"])
            _night_light_active = True
        return True
    except Exception as e:
        logger.error(f"[Modus] Failed to toggle night light: {e}")
        return False


def is_night_light_active() -> bool:
    global _night_light_active
    if _night_light_active:
        return True
    try:
        _night_light_active = bool(find_process_pid("hyprsunset"))
        return _night_light_active
    except Exception:
        return False


# --- Caffeine orchestration ---


def is_caffeine_active() -> bool:
    return get_inhibit_service().active


def toggle_caffeine() -> bool:
    return get_inhibit_service().toggle()


# --- Hyprland window management API ---


def _ensure_hyprland():
    """Ensure hyprland_connection is initialized."""
    global _hyprland_connection
    if _hyprland_connection is None:
        get_modus_service()
    return _hyprland_connection


def _hyprctl_send(cmd: str) -> bytes | None:
    conn = _ensure_hyprland()
    if not conn:
        return None
    try:
        reply = conn.send_command(cmd).reply
        return reply
    except Exception as e:
        logger.error(f"[Modus] hyprctl send error ({cmd}): {e}")
        return None


def _hyprctl_json(cmd: str) -> list | dict | None:
    reply = _hyprctl_send(cmd)
    if not reply:
        return None
    try:
        return json.loads(reply.decode("utf-8"))
    except Exception as e:
        logger.error(f"[Modus] hyprctl JSON parse error ({cmd}): {e}")
        return None


def get_clients() -> list:
    data = _hyprctl_json("j/clients")
    return data if isinstance(data, list) else []


def get_active_window() -> dict:
    data = _hyprctl_json("j/activewindow")
    return data if isinstance(data, dict) else {}


def get_monitors() -> list:
    data = _hyprctl_json("j/monitors")
    return data if isinstance(data, list) else []


def get_focused_monitor() -> dict | None:
    monitors = get_monitors()
    for monitor in monitors:
        if monitor.get("focused"):
            return monitor
    return monitors[0] if monitors else None


def get_monitor_names() -> list[str]:
    return [name for m in get_monitors() if (name := m.get("name"))]


def get_active_monitor_name(fallback: str = "eDP-1") -> str:
    monitor = get_focused_monitor()
    if monitor and (name := monitor.get("name")):
        return name
    return fallback


def get_active_workspace_id() -> int:
    data = _hyprctl_json("j/activeworkspace")
    if isinstance(data, dict):
        return data.get("id", -1)
    return -1


def get_monitor_for_workspace(workspace_id: int | None = None) -> dict | None:
    if workspace_id is None:
        workspace_id = get_active_workspace_id()
    for monitor in get_monitors():
        if monitor.get("activeWorkspace", {}).get("id") == workspace_id:
            return monitor
    monitors = get_monitors()
    return monitors[0] if monitors else None


def get_screen_dimensions() -> tuple[int, int]:
    monitor = get_monitor_for_workspace()
    if monitor:
        return monitor.get("width", 1920), monitor.get("height", 1080)
    return 1920, 1080


def focus_window(address: str):
    exec_shell_command_async(
        f"hyprctl dispatch 'hl.dsp.focus({{ window = \"address:{address}\" }})'"
    )


def close_window(address: str):
    exec_shell_command_async(
        f"hyprctl dispatch 'hl.dsp.window.close({{ window = \"address:{address}\" }})'"
    )


def launch_app(command_line: str):
    from globalmenu.launch import launch_command

    launch_command(command_line)


def open_trash():
    trash_path = os.path.expanduser("~/.local/share/Trash/files")
    if not os.path.exists(trash_path):
        return
    for fm in ["nautilus", "dolphin", "thunar", "nemo", "caja", "pcmanfm"]:
        try:
            if find_binary(fm):
                spawn_detached([fm, trash_path])
                return
        except Exception:
            continue


# Occlusion
def check_occlusion(occlusion_region, workspace=None) -> bool:
    if workspace is None:
        workspace = get_active_workspace_id()

    if isinstance(occlusion_region, tuple) and len(occlusion_region) == 2:
        side, size = occlusion_region
        if isinstance(side, str):
            screen_width, screen_height = get_screen_dimensions()
            if side.lower() == "bottom":
                occlusion_region = (0, screen_height - size, screen_width, size)
            elif side.lower() == "top":
                occlusion_region = (0, 0, screen_width, size)
            elif side.lower() == "left":
                occlusion_region = (0, 0, size, screen_height)
            elif side.lower() == "right":
                occlusion_region = (screen_width - size, 0, size, screen_height)

    if not isinstance(occlusion_region, tuple) or len(occlusion_region) != 4:
        return False

    clients = get_clients()
    occ_x, occ_y, occ_width, occ_height = occlusion_region
    occ_x2 = occ_x + occ_width
    occ_y2 = occ_y + occ_height

    for client in clients:
        if not client.get("mapped", False):
            continue
        client_workspace = client.get("workspace", {})
        if client_workspace.get("id") != workspace:
            continue
        position = client.get("at")
        size = client.get("size")
        if not position or not size:
            continue
        x, y = position
        width, height = size
        win_x1, win_y1 = x, y
        win_x2, win_y2 = x + width, y + height
        if not (
            win_x2 <= occ_x or win_x1 >= occ_x2 or win_y2 <= occ_y or win_y1 >= occ_y2
        ):
            return True
    return False
