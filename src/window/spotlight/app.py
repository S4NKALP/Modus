from fabric import Application
from fabric.core.service import Service
from fabric.utils import GLib, get_relative_path, logger
from gi.repository import Gio

from shared.data import load_config
from utils.functions import set_process_name
from window.spotlight.main import SpotlightWindow

BUS_NAME = "dev.modus.Spotlight"
OBJECT_PATH = "/dev/modus/Spotlight"
INTERFACE = "dev.modus.Spotlight"

_INTROSPECTION = f"""<node>
  <interface name='{INTERFACE}'>
    <method name='Toggle'>
      <arg type='s' name='command' direction='in'/>
      <arg type='s' name='text' direction='in'/>
      <arg type='b' name='external' direction='in'/>
    </method>
  </interface>
</node>"""


class SpotlightService(Service):
    """DBus-exposed controller for the running spotlight instance.

    Owns no state of its own; it forwards IPC calls to the live window.
    """

    def __init__(self, window: SpotlightWindow, **kwargs):
        super().__init__(**kwargs)
        self._window = window
        self._connection = Gio.bus_get_sync(Gio.BusType.SESSION)
        self._reg_id = self._connection.register_object(
            OBJECT_PATH,
            Gio.DBusNodeInfo.new_for_xml(_INTROSPECTION).interfaces[0],
            self._on_method_call,
        )

    def _on_method_call(
        self,
        _conn,
        _sender,
        _path,
        _iface,
        method,
        params,
        invocation,
    ):
        if method == "Toggle":
            command, text, external = params.unpack()
            GLib.idle_add(lambda: self._window.toggle(command, text, external=external))
        invocation.return_value(None)

    def release(self):
        if self._reg_id:
            self._connection.unregister_object(self._reg_id)
            self._reg_id = 0


def _request_name() -> int:
    """Try to own the spotlight bus name. Returns the RequestName reply code
    (1 == primary owner)."""
    conn = Gio.bus_get_sync(Gio.BusType.SESSION)
    reply = conn.call_sync(
        "org.freedesktop.DBus",
        "/org/freedesktop/DBus",
        "org.freedesktop.DBus",
        "RequestName",
        GLib.Variant("(su)", (BUS_NAME, 0)),
        GLib.VariantType.new("(u)"),
        Gio.DBusCallFlags.NONE,
        -1,
        None,
    )
    return reply.get_child_value(0).get_uint32()


def _forward_to_running(command: str, text: str, external: bool) -> bool:
    """Hand the command to an already-running instance. Return True on success."""
    try:
        conn = Gio.bus_get_sync(Gio.BusType.SESSION)
        conn.call_sync(
            BUS_NAME,
            OBJECT_PATH,
            INTERFACE,
            "Toggle",
            GLib.Variant("(ssb)", (command, text, external)),
            None,
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )
        return True
    except GLib.Error as e:
        logger.warning(
            f"[Spotlight] failed to forward to running instance: {e.message}"
        )
        return False


def main(command: str = "", text: str = "", external: bool = False):
    # If an instance already owns the bus name, let it handle the toggle and
    # exit. This is the same on-demand forwarding the old socket did.
    if _request_name() != 1:
        _forward_to_running(command, text, external)
        return

    set_process_name("modus-spotlight")
    load_config()

    spotlight = SpotlightWindow()

    global app
    app = Application("modus-spotlight", spotlight)

    def set_css():
        app.set_stylesheet_from_file(get_relative_path("../../styles/main.css"))

    app.set_css = set_css
    app.set_css()

    # Kill the process on every dismissal so nothing lingers in memory.
    # close_spotlight is the single close chokepoint (Escape, result launch,
    # and toggle-when-visible all route through it).
    _orig_close = spotlight.close_spotlight

    def _close_and_quit():
        _orig_close()
        app.quit()

    spotlight.close_spotlight = _close_and_quit

    service = SpotlightService(spotlight)

    spotlight.toggle(command, text, external=external)

    # External one-shot commands never show the window; give any async action a
    # moment to fire, then exit so we do not stay resident.
    if external and not spotlight.get_visible():
        GLib.timeout_add(2000, app.quit)

    try:
        app.run()
    finally:
        service.release()
