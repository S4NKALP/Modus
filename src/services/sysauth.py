"""Polkit authentication agent service for Modus.

Registers as a Polkit authentication agent on the D-Bus session bus
and listens for authentication requests from polkitd. Emits signals
so the UI layer can show a password dialog.

D-Bus flow:
1. Export org.freedesktop.PolicyKit1.AuthenticationAgent on system bus
2. Register with Polkit Authority on system bus
3. polkitd calls BeginAuthentication → service emits signal
4. UI responds via respond(cookie, password)

polkitd addresses the agent by the system-bus unique name it called
RegisterAuthenticationAgent with, so the agent object must be exported
on the system bus (not the session bus).
"""

import os
import pwd
import socket
import subprocess

from fabric.core.service import Service, Signal
from fabric.utils import Gio, GLib, logger

POLKIT_BUS_NAME = "org.freedesktop.PolicyKit1"
POLKIT_AUTHORITY_PATH = "/org/freedesktop/PolicyKit1/Authority"
POLKIT_AUTHORITY_IFACE = "org.freedesktop.PolicyKit1.Authority"

AGENT_OBJECT_PATH = "/org/freedesktop/PolicyKit1/AuthenticationAgent"
AGENT_INTERFACE = "org.freedesktop.PolicyKit1.AuthenticationAgent"

AGENT_HELPER_SOCKET = "/run/polkit/agent-helper.socket"
AGENT_HELPER_PATH = "/usr/lib/polkit-1/polkit-agent-helper-1"
HELPER_TIMEOUT = 15

AGENT_INTROSPECTION = """<!DOCTYPE node>
<node>
  <interface name="org.freedesktop.PolicyKit1.AuthenticationAgent">
    <method name="BeginAuthentication">
      <arg name="action_id" type="s" direction="in"/>
      <arg name="message" type="s" direction="in"/>
      <arg name="icon_name" type="s" direction="in"/>
      <arg name="details" type="a{ss}" direction="in"/>
      <arg name="cookie" type="s" direction="in"/>
      <arg name="identities" type="a(sa{sv})" direction="in"/>
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

        self._agent_registration_id = None
        self._authority_proxy = None
        self._registered = False
        self._registered_subject = None
        self._pending = {}

    def start(self) -> bool:
        """Start the agent: export on system bus and register with Authority.

        Returns:
            True if registration succeeded, False otherwise.
        """
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            if bus is None:
                logger.error("[SysauthService] Cannot get system bus")
                return False

            node_info = Gio.DBusNodeInfo.new_for_xml(AGENT_INTROSPECTION)
            interface_info = node_info.lookup_interface(AGENT_INTERFACE)

            self._agent_registration_id = bus.register_object_with_closures2(
                AGENT_OBJECT_PATH,
                interface_info,
                self._handle_method_call,
            )

            logger.info(
                f"[SysauthService] Exported agent on system bus at {AGENT_OBJECT_PATH}"
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
        if self._agent_registration_id is not None:
            try:
                bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
                if bus is not None:
                    bus.unregister_object(self._agent_registration_id)
            except GLib.Error:
                pass
            self._agent_registration_id = None

        if self._registered:
            self._unregister_from_authority()
            self._registered = False

        for pending in self._pending.values():
            invocation = pending["invocation"]
            GLib.idle_add(lambda: invocation.return_value(None))
        self._pending.clear()

        logger.info("[SysauthService] Stopped")

    def respond(self, cookie: str, password: str) -> bool:
        """Send authentication response back to polkitd.

        Delegates to the polkit-agent-helper-1 helper (preferring the
        systemd socket-activation path), which performs the PAM
        authentication and invokes AuthenticationAgentResponse2/3 on the
        Authority as root. Direct D-Bus response calls only accept uid 0.

        On success the held BeginAuthentication reply is returned, which
        is what completes the pending session in polkitd. On failure the
        reply stays pending so the UI can re-prompt with the same cookie.

        Args:
            cookie: The authentication session cookie.
            password: The password to send.

        Returns:
            True if authentication succeeded, False otherwise.
        """
        pending = self._pending.get(cookie)
        if pending is None:
            logger.warning(
                f"[SysauthService] respond() called for unknown cookie {cookie[:16]}"
            )
            return False

        uid = pending["uid"]
        invocation = pending["invocation"]

        try:
            username = pwd.getpwuid(uid).pw_name
        except (KeyError, OverflowError):
            logger.error(f"[SysauthService] No user found for uid {uid}")
            return False

        success = self._run_helper(cookie, password, username)

        if success:
            self._pending.pop(cookie, None)
            GLib.idle_add(lambda: invocation.return_value(None))

        GLib.idle_add(lambda: self.emit("authentication-completed", cookie, success))
        return success

    def cancel(self, cookie: str) -> None:
        """Cancel a pending authentication request from the UI side.

        Returns the held BeginAuthentication reply with a cancelled
        error so polkitd marks the session as dismissed.
        """
        pending = self._pending.pop(cookie, None)
        if pending is None:
            return

        invocation = pending["invocation"]
        GLib.idle_add(
            lambda: invocation.return_error_literal(
                "org.freedesktop.PolicyKit1.Error.Cancelled",
                "Authentication cancelled by user",
            )
        )
        GLib.idle_add(lambda: self.emit("authentication-cancelled", cookie))

    def _run_helper(self, cookie: str, password: str, username: str) -> bool:
        """Run polkit-agent-helper-1 via socket activation or setuid binary."""
        if os.path.exists(AGENT_HELPER_SOCKET):
            try:
                return self._run_helper_via_socket(cookie, password, username)
            except (TimeoutError, OSError) as e:
                logger.warning(
                    f"[SysauthService] Socket helper failed, falling back to "
                    f"setuid helper: {e}"
                )

        if not os.path.exists(AGENT_HELPER_PATH):
            logger.error(
                f"[SysauthService] No authentication helper available at "
                f"{AGENT_HELPER_PATH}"
            )
            return False

        return self._run_helper_setuid(cookie, password, username)

    def _run_helper_via_socket(self, cookie: str, password: str, username: str) -> bool:
        """Authenticate through the polkit-agent-helper systemd socket.

        The helper reads the username and cookie from the first two input
        lines, then the password when PAM prompts for it. Answering each
        prompt keeps the conversation flowing.
        """
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(HELPER_TIMEOUT)
        with sock, sock.makefile("rwb") as stream:
            sock.connect(AGENT_HELPER_SOCKET)
            stream.write(username.encode() + b"\n")
            stream.write(cookie.encode() + b"\n")
            stream.write(password.encode() + b"\n")
            stream.flush()

            answered = False
            for raw in stream:
                line = raw.decode(errors="replace").strip()
                if line.startswith("PAM_PROMPT_"):
                    stream.write((password if not answered else "").encode() + b"\n")
                    stream.flush()
                    answered = True
                elif line == "SUCCESS":
                    return True
                elif line == "FAILURE":
                    return False
        return False

    def _run_helper_setuid(self, cookie: str, password: str, username: str) -> bool:
        """Authenticate through the setuid polkit-agent-helper-1 binary."""
        try:
            proc = subprocess.run(
                [AGENT_HELPER_PATH, username, cookie],
                input=password + "\n",
                capture_output=True,
                text=True,
                timeout=HELPER_TIMEOUT,
                check=False,
            )
        except subprocess.TimeoutExpired:
            logger.error("[SysauthService] Setuid helper timed out")
            return False

        output = (proc.stdout or "").strip()
        return output.endswith("SUCCESS")

    def _register_with_authority(self) -> bool:
        """Register this agent with the Polkit Authority on the system bus.

        polkit's Authority exposes the eggdbus-style signature
        ``RegisterAuthenticationAgent((sa{sv}) subject, s locale,
        s object_path)``. A session subject (matching how desktop agents
        register) is preferred so every request in the session routes to
        this agent; the process subject is the fallback.
        """
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

            locale = os.environ.get("LANG", "en_US.UTF-8")

            candidates = [self._process_subject()]
            session_subject = self._session_subject()
            if session_subject is not None:
                candidates.insert(0, session_subject)

            for kind, details in candidates:
                builder = GLib.VariantBuilder(GLib.VariantType("((sa{sv})ss)"))
                builder.add_value(self._subject_variant(kind, details))
                builder.add_value(GLib.Variant("s", locale))
                builder.add_value(GLib.Variant("s", AGENT_OBJECT_PATH))
                try:
                    self._authority_proxy.call_sync(
                        "RegisterAuthenticationAgent",
                        builder.end(),
                        Gio.DBusCallFlags.NONE,
                        -1,
                        None,
                    )
                except GLib.Error as e:
                    error_msg = str(e)
                    if kind == "unix-session" and "already exists" in error_msg:
                        logger.warning(
                            "[SysauthService] Session agent already registered "
                            "(another agent owns this session). Falling back to "
                            "process-scope registration: only requests originating "
                            "from this process will route here."
                        )
                    else:
                        logger.warning(
                            f"[SysauthService] Register with {kind} subject failed: {e}"
                        )
                    continue

                self._registered = True
                self._registered_subject = (kind, details)

                if kind == "unix-session":
                    logger.info(
                        "[SysauthService] Registered with Authority "
                        f"(session subject, PID {os.getpid()})"
                    )
                else:
                    logger.warning(
                        "[SysauthService] Registered with Authority using "
                        f"process-scope subject (PID {os.getpid()}). "
                        "Only requests from this process will be handled. "
                        "To integrate with the full session, stop the "
                        "existing agent (e.g. polkit-gnome-authentication-agent-1)."
                    )
                return True

            return False

        except GLib.Error as e:
            logger.error(f"[SysauthService] Registration failed: {e}")
            return False

    def _unregister_from_authority(self) -> None:
        """Unregister this agent from the Polkit Authority."""
        if self._authority_proxy is None or self._registered_subject is None:
            return

        try:
            kind, details = self._registered_subject

            builder = GLib.VariantBuilder(GLib.VariantType("((sa{sv})s)"))
            builder.add_value(self._subject_variant(kind, details))
            builder.add_value(GLib.Variant("s", AGENT_OBJECT_PATH))

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

    def _session_subject(self) -> "tuple[str, dict] | None":
        """Build a unix-session subject from the current session, if known."""
        session_id = os.environ.get("XDG_SESSION_ID")
        if not session_id:
            return None
        return ("unix-session", {"session-id": session_id})

    def _process_subject(self) -> "tuple[str, dict]":
        """Build a unix-process subject for this process.

        polkit requires the ``start-time`` key (field 22 of
        ``/proc/<pid>/stat``, in clock ticks) alongside ``pid`` to
        validate the subject.
        """
        details: dict = {"pid": os.getpid()}
        start_time = self._process_start_time(os.getpid())
        if start_time is not None:
            details["start-time"] = start_time
        return ("unix-process", details)

    @staticmethod
    def _process_start_time(pid: int) -> "int | None":
        """Read the process start time from /proc (field 22, clock ticks)."""
        try:
            with open(f"/proc/{pid}/stat") as f:
                data = f.read()
        except OSError:
            return None
        name_end = data.rfind(")")
        if name_end < 0:
            return None
        fields = data[name_end + 2 :].split()
        if len(fields) < 20:
            return None
        try:
            return int(fields[19])
        except (ValueError, IndexError):
            return None

    def _subject_variant(self, kind: str, details: dict) -> GLib.Variant:
        """Build the ``(sa{sv})`` subject struct for the Authority."""
        subject_builder = GLib.VariantBuilder(GLib.VariantType("(sa{sv})"))
        subject_builder.add_value(GLib.Variant("s", kind))

        details_builder = GLib.VariantBuilder(GLib.VariantType("a{sv}"))
        for key, value in details.items():
            if key == "pid":
                variant = GLib.Variant("u", value)
            elif key == "start-time":
                variant = GLib.Variant("t", value)
            else:
                variant = GLib.Variant("s", str(value))
            details_builder.add_value(GLib.Variant("{sv}", (key, variant)))
        subject_builder.add_value(details_builder.end())

        return subject_builder.end()

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
        """Handle BeginAuthentication call from polkitd.

        The D-Bus reply is deliberately held back: polkitd completes the
        authentication session only when this method returns, so the
        reply is sent once authentication resolves (see respond()/cancel()).
        """
        action_id, message, icon_name, _details, cookie, identities = (
            parameters.unpack()
        )

        uid = -1
        if identities:
            for kind, value in identities:
                if kind == "unix-user" and isinstance(value, dict):
                    uid = value.get("uid", -1)
                    break

        if uid == -1:
            uid = os.getuid()

        self._pending[cookie] = {"uid": uid, "invocation": invocation}

        processed_action = _process_action_id(action_id, message)

        logger.info(
            f"[SysauthService] BeginAuthentication: action={processed_action} "
            f"uid={uid} cookie={cookie[:16]}..."
        )

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

        pending = self._pending.pop(cookie, None)
        if pending is not None:
            GLib.idle_add(lambda: pending["invocation"].return_value(None))

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
