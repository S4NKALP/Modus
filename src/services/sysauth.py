"""Polkit authentication agent service for Modus.

Registers as a Polkit authentication agent on the D-Bus session bus
and listens for authentication requests from polkitd. Emits signals
so the UI layer can show a password dialog.

D-Bus flow:
1. Export org.freedesktop.PolicyKit1.AuthenticationAgent on session bus
2. Register with Polkit Authority on system bus
3. polkitd calls BeginAuthentication → service emits signal
4. UI responds via respond(cookie, password)
"""

import os

from fabric.core.service import Service, Signal
from fabric.utils import Gio, GLib, logger

POLKIT_BUS_NAME = "org.freedesktop.PolicyKit1"
POLKIT_AUTHORITY_PATH = "/org/freedesktop/PolicyKit1/Authority"
POLKIT_AUTHORITY_IFACE = "org.freedesktop.PolicyKit1.Authority"

AGENT_OBJECT_PATH = "/org/freedesktop/PolicyKit1/AuthenticationAgent"
AGENT_INTERFACE = "org.freedesktop.PolicyKit1.AuthenticationAgent"

AGENT_INTROSPECTION = """<!DOCTYPE node>
<node>
  <interface name="org.freedesktop.PolicyKit1.AuthenticationAgent">
    <method name="BeginAuthentication">
      <arg name="action_id" type="s" direction="in"/>
      <arg name="message" type="s" direction="in"/>
      <arg name="icon_name" type="s" direction="in"/>
      <arg name="details" type="a{ss}" direction="in"/>
      <arg name="cookie" type="s" direction="in"/>
      <arg name="identities" type="a(si)" direction="in"/>
    </method>
    <method name="CancelAuthentication">
      <arg name="cookie" type="s" direction="in"/>
    </method>
  </interface>
</node>
"""


class SysauthService(Service):
    """Polkit authentication agent as a Modus service.

    Registers with polkitd and emits signals when authentication
    is requested. The UI layer connects to these signals to show
    a password dialog.
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @Signal
    def begin_authentication(
        self, action_id: str, message: str, icon_name: str, cookie: str, uid: int
    ) -> None:
        """Emitted when polkitd requests authentication.

        Args:
            action_id: Processed action identifier (human-readable).
            message: Description of the action requiring auth.
            icon_name: Icon name for the action.
            cookie: Session cookie for responding.
            uid: User ID being authenticated.
        """

    @Signal
    def authentication_cancelled(self, cookie: str) -> None:
        """Emitted when polkitd cancels an authentication request."""

    @Signal
    def authentication_completed(self, cookie: str, success: bool) -> None:
        """Emitted when authentication completes (success or failure)."""

    def __init__(self, **kwargs):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        super().__init__(**kwargs)

        self._session_bus_id = None
        self._authority_proxy = None
        self._registered = False

    def start(self) -> bool:
        """Start the agent: export on session bus and register with Authority.

        Returns:
            True if registration succeeded, False otherwise.
        """
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            if bus is None:
                logger.error("[SysauthService] Cannot get session bus")
                return False

            node_info = Gio.DBusNodeInfo.new_for_xml(AGENT_INTROSPECTION)
            interface_info = node_info.lookup_interface(AGENT_INTERFACE)

            self._session_bus_id = bus.register_object_with_closures2(
                AGENT_OBJECT_PATH,
                interface_info,
                self._handle_method_call,
            )

            logger.info(
                f"[SysauthService] Exported agent on session bus at {AGENT_OBJECT_PATH}"
            )

            if not self._register_with_authority():
                logger.warning(
                    "[SysauthService] Failed to register with Authority, "
                    "running without polkit integration"
                )
                return False

            return True

        except GLib.Error as e:
            logger.error(f"[SysauthService] Failed to start: {e}")
            return False

    def stop(self) -> None:
        """Unregister and clean up D-Bus resources."""
        if self._session_bus_id is not None:
            try:
                bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
                if bus is not None:
                    bus.unregister_object(self._session_bus_id)
            except GLib.Error:
                pass
            self._session_bus_id = None

        if self._registered:
            self._unregister_from_authority()
            self._registered = False

        logger.info("[SysauthService] Stopped")

    def respond(self, cookie: str, password: str) -> None:
        """Send authentication response back to polkitd.

        Args:
            cookie: The authentication session cookie.
            password: The password to send.
        """
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            if bus is None:
                logger.error("[SysauthService] Cannot get session bus for response")
                return

            bus.call_sync(
                POLKIT_BUS_NAME,
                AGENT_OBJECT_PATH,
                AGENT_INTERFACE,
                "Respond",
                GLib.Variant("(ss)", (cookie, password)),
                None,
                Gio.DBusCallFlags.NONE,
                -1,
                None,
            )
        except GLib.Error as e:
            logger.error(f"[SysauthService] Failed to send response: {e}")

    def _register_with_authority(self) -> bool:
        """Register this agent with the Polkit Authority on the system bus."""
        try:
            system_bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            if system_bus is None:
                logger.error("[SysauthService] Cannot get system bus")
                return False

            self._authority_proxy = Gio.DBusProxy.new_sync(
                system_bus,
                Gio.DBusProxyFlags.NONE,
                None,
                POLKIT_BUS_NAME,
                POLKIT_AUTHORITY_PATH,
                POLKIT_AUTHORITY_IFACE,
                None,
            )

            pid = os.getpid()
            locale = os.environ.get("LANG", "en_US.UTF-8")

            builder = GLib.VariantBuilder(GLib.VariantType("(sa{sv}so)"))
            builder.add_value(GLib.Variant("s", "unix-process"))
            details = GLib.VariantBuilder(GLib.VariantType("a{sv}"))
            details.add_value(GLib.Variant("{sv}", ("pid", GLib.Variant("u", pid))))
            builder.add_value(details.end())
            builder.add_value(GLib.Variant("s", locale))
            builder.add_value(GLib.Variant("o", AGENT_OBJECT_PATH))

            self._authority_proxy.call_sync(
                "RegisterAuthenticationAgent",
                builder.end(),
                Gio.DBusCallFlags.NONE,
                -1,
                None,
            )

            self._registered = True
            logger.info(f"[SysauthService] Registered with Authority (PID {pid})")
            return True

        except GLib.Error as e:
            logger.error(f"[SysauthService] Registration failed: {e}")
            return False

    def _unregister_from_authority(self) -> None:
        """Unregister this agent from the Polkit Authority."""
        if self._authority_proxy is None:
            return

        try:
            pid = os.getpid()

            builder = GLib.VariantBuilder(GLib.VariantType("(sa{sv}o)"))
            builder.add_value(GLib.Variant("s", "unix-process"))
            details = GLib.VariantBuilder(GLib.VariantType("a{sv}"))
            details.add_value(GLib.Variant("{sv}", ("pid", GLib.Variant("u", pid))))
            builder.add_value(details.end())
            builder.add_value(GLib.Variant("o", AGENT_OBJECT_PATH))

            self._authority_proxy.call_sync(
                "UnregisterAuthenticationAgent",
                builder.end(),
                Gio.DBusCallFlags.NONE,
                -1,
                None,
            )

            logger.info("[SysauthService] Unregistered from Authority")
        except GLib.Error as e:
            logger.warning(f"[SysauthService] Unregister failed: {e}")

    def _handle_method_call(
        self,
        connection: Gio.DBusConnection,
        sender: str,
        object_path: str,
        interface_name: str,
        method_name: str,
        parameters: GLib.Variant,
        invocation: Gio.DBusMethodInvocation,
    ) -> None:
        """Handle incoming D-Bus method calls from polkitd."""
        if method_name == "BeginAuthentication":
            self._handle_begin_authentication(parameters, invocation)
        elif method_name == "CancelAuthentication":
            self._handle_cancel_authentication(parameters, invocation)
        else:
            invocation.return_error_literal(
                Gio.DBusError,
                Gio.DBusError.UNKNOWN_METHOD,
                f"Unknown method: {method_name}",
            )

    def _handle_begin_authentication(
        self,
        parameters: GLib.Variant,
        invocation: Gio.DBusMethodInvocation,
    ) -> None:
        """Handle BeginAuthentication call from polkitd."""
        action_id, message, icon_name, _details, cookie, identities = (
            parameters.unpack()
        )

        uid = -1
        if identities:
            for kind, value in identities:
                if kind == "unix-user":
                    if isinstance(value, dict):
                        uid = value.get("uid", -1)
                    elif isinstance(value, int):
                        uid = value
                    elif isinstance(value, tuple):
                        uid = value[0] if value else -1
                    break

        if uid == -1:
            uid = os.getuid()

        processed_action = _process_action_id(action_id, message)

        logger.info(
            f"[SysauthService] BeginAuthentication: action={processed_action} "
            f"uid={uid} cookie={cookie[:16]}..."
        )

        invocation.return_value(None)

        GLib.idle_add(
            lambda: self.emit(
                "begin-authentication",
                processed_action,
                message,
                icon_name,
                cookie,
                uid,
            )
        )

    def _handle_cancel_authentication(
        self,
        parameters: GLib.Variant,
        invocation: Gio.DBusMethodInvocation,
    ) -> None:
        """Handle CancelAuthentication call from polkitd."""
        (cookie,) = parameters.unpack()
        logger.info(f"[SysauthService] CancelAuthentication: cookie={cookie[:16]}")
        invocation.return_value(None)
        GLib.idle_add(lambda: self.emit("authentication-cancelled", cookie))


def _process_action_id(action_id: str, message: str) -> str:
    """Process action_id to extract a human-readable name.

    Matches the C++ sysauth behavior:
    - For org.freedesktop.policykit.exec: extracts program name from message
    - For other actions: strips everything before the last dot
    """
    if action_id == "org.freedesktop.policykit.exec":
        try:
            start = message.rfind("/") + 1
            end = message.find("'", start)
            if start > 0 and end > start:
                return message[start:end]
        except (ValueError, IndexError):
            pass
        return action_id

    if "." in action_id:
        return action_id.rsplit(".", 1)[-1]

    return action_id


def get_sysauth_service() -> SysauthService:
    """Get the singleton sysauth service instance."""
    return SysauthService()
