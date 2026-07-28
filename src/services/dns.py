import subprocess
import threading

from fabric.utils import GLib, logger

DEFAULT_PROVIDERS = [
    {"label": "Cloudflare", "primary": "1.1.1.1", "secondary": "1.0.0.1"},
    {"label": "Google", "primary": "8.8.8.8", "secondary": "8.8.4.4"},
    {"label": "OpenDNS", "primary": "208.67.222.222", "secondary": "208.67.220.220"},
    {"label": "AdGuard", "primary": "94.140.14.14", "secondary": "94.140.15.15"},
    {"label": "Quad9", "primary": "9.9.9.9", "secondary": "149.112.112.112"},
]


def _nmcli(*args, timeout=15):
    """Run nmcli and return (returncode, stdout, stderr)."""
    try:
        r = subprocess.run(
            ["nmcli", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except FileNotFoundError:
        logger.warning("[Dns] nmcli not found")
        return 127, "", "nmcli not found"
    except subprocess.TimeoutExpired:
        logger.warning("[Dns] nmcli timed out")
        return -1, "", "timeout"
    except Exception as e:
        logger.error(f"[Dns] nmcli failed: {e}")
        return 1, "", str(e)


def _active_connection_name():
    """Return the NM connection name (id) of the first active connection."""
    rc, out, _ = _nmcli("-t", "-f", "NAME,DEVICE", "connection", "show", "--active")
    if rc != 0 or not out:
        return None
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) >= 2:
            return parts[0]
    return None


def _active_device():
    """Return the interface name of the first active wifi/ethernet device."""
    rc, out, _ = _nmcli("-t", "-f", "DEVICE,TYPE,STATE", "device", "status")
    if rc != 0 or not out:
        return None
    for line in out.splitlines():
        parts = line.split(":")
        if (
            len(parts) >= 3
            and parts[1] in ("wifi", "ethernet")
            and parts[2] == "connected"
        ):
            return parts[0]
    return None


def get_dns(callback=None):
    """Get current IPv4 DNS servers for the active connection.

    Returns an empty list when DHCP-provided DNS is in use (auto mode).
    Calls ``callback(dns_servers: list[str])`` on the main thread.
    """

    def _work():
        try:
            conn_name = _active_connection_name()
            if not conn_name:
                GLib.idle_add(callback, []) if callback else None
                return

            # Check if custom DNS is enabled
            rc, out, _ = _nmcli(
                "-t",
                "-f",
                "ipv4.ignore-auto-dns",
                "connection",
                "show",
                conn_name,
            )
            if rc == 0 and out.strip() == "no":
                GLib.idle_add(callback, []) if callback else None
                return

            rc, out, _ = _nmcli("-t", "-f", "ipv4.dns", "connection", "show", conn_name)
            if rc != 0 or not out:
                GLib.idle_add(callback, []) if callback else None
                return
            servers = []
            for line in out.splitlines():
                line = line.strip()
                if line and line != "--":
                    servers.append(line)
            GLib.idle_add(callback, servers) if callback else None
        except Exception as e:
            logger.error(f"[Dns] Failed to get DNS: {e}")
            if callback:
                GLib.idle_add(callback, [])

    threading.Thread(target=_work, daemon=True).start()


def set_dns(dns_servers, callback=None):
    """Set IPv4 DNS servers on the active connection and apply.

    Pass an empty list to clear custom DNS (revert to DHCP).
    Manual DNS uses ``device reapply`` for instant effect.
    Auto mode uses ``connection up`` because DHCP renew is required.
    Calls ``callback(success: bool)`` on the main thread.
    """

    def _work():
        try:
            conn_name = _active_connection_name()
            if not conn_name:
                logger.warning("[Dns] No active connection")
                if callback:
                    GLib.idle_add(callback, False)
                return

            if dns_servers:
                for server in dns_servers:
                    rc, _, err = _nmcli(
                        "connection", "modify", conn_name, "ipv4.dns", server
                    )
                    if rc != 0:
                        logger.warning(f"[Dns] Failed to set dns {server}: {err}")
                _nmcli(
                    "connection",
                    "modify",
                    conn_name,
                    "ipv4.ignore-auto-dns",
                    "yes",
                )
                # Fast apply for manual DNS
                device = _active_device()
                if device:
                    rc, _, err = _nmcli("device", "reapply", device, timeout=10)
                    if rc != 0:
                        logger.warning(
                            f"[Dns] reapply failed ({device}): {err}, "
                            "falling back to connection up"
                        )
                        rc, _, err = _nmcli("connection", "up", conn_name, timeout=20)
                else:
                    rc, _, err = _nmcli("connection", "up", conn_name, timeout=20)
            else:
                # Revert to DHCP — must reconnect to renew DHCP DNS
                _nmcli(
                    "connection",
                    "modify",
                    conn_name,
                    "ipv4.ignore-auto-dns",
                    "no",
                )
                rc, _, err = _nmcli("connection", "up", conn_name, timeout=20)

            ok = rc == 0
            if ok:
                logger.info(f"[Dns] DNS set to {dns_servers or 'auto'}")
            else:
                logger.warning(f"[Dns] apply failed: {err}")
            if callback:
                GLib.idle_add(callback, ok)
        except Exception as e:
            logger.error(f"[Dns] Failed to set DNS: {e}")
            if callback:
                GLib.idle_add(callback, False)

    threading.Thread(target=_work, daemon=True).start()
