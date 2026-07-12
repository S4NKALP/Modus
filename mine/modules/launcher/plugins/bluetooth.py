from __future__ import annotations

import shlex
from collections.abc import Iterator
from typing import Any

from fabric.bluetooth import BluetoothClient
from fabric.utils import GLib, idle_add, remove_handler
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label

from modules.launcher.base import LauncherPlugin
from utils.functions import run_command


class BluetoothPlugin(LauncherPlugin):
    @property
    def name(self) -> str:
        return "bluetooth"

    @property
    def icon(self) -> str:
        return "bluetooth"

    @property
    def keywords(self) -> list[str]:
        return ["bt"]

    def __init__(self, handler):
        super().__init__(handler)
        self._query_handler: int = 0
        self._signal_refresh_handler: int = 0
        self._is_active: bool = False

        self._client = BluetoothClient()

        if self._client is not None:
            self._client.connect("device-added", lambda *_: self._on_bt_changed())
            self._client.connect("notify::enabled", lambda *_: self._on_bt_changed())
            self._client.connect("notify::scanning", lambda *_: self._on_bt_changed())
        self._signal_matches = []
        self.current_slots: list = []

    def on_search(self, text: str) -> None:
        self.query_bluetooth(text)

    def stop(self):
        if self._query_handler:
            remove_handler(self._query_handler)
            self._query_handler = 0
        if self._signal_refresh_handler:
            GLib.source_remove(self._signal_refresh_handler)
            self._signal_refresh_handler = 0
        self._signal_matches.clear()
        self.current_slots.clear()

    def query_bluetooth(self, text: str) -> None:
        self._is_active = True
        self.handler.start("bluetooth")
        self.current_slots.clear()

        text_stripped = text.strip()
        commands = {
            "power": self._handle_power_command,
            "scan": self._handle_scan_command,
            "connect": self._handle_connect_command,
            "disconnect": self._handle_disconnect_command,
            "help": lambda t: self._show_help(),
        }

        for prefix, handler in commands.items():
            if text_stripped.lower().startswith(prefix):
                handler(text_stripped)
                return

        if (
            self._client is not None
            and hasattr(self._client, "scanning")
            and self._client.scanning
        ):  # type: ignore
            self._show_scanning_indicator()

        items = self._enumerate(text)
        if not items:
            self._show_empty()
            return
        self._query_handler = idle_add(self._bake_next_slot, iter(items), pin=True)

    def _on_bt_changed(self, *args, **kwargs):
        if not self._is_active:
            return
        if self._signal_refresh_handler:
            return
        self._signal_refresh_handler = GLib.timeout_add(250, self._on_refresh_timeout)

    def _on_refresh_timeout(self) -> bool:
        self._signal_refresh_handler = 0
        if self._is_active:
            self.handler.start("bluetooth")
            if hasattr(self.handler, "clear_viewport"):
                self.handler.clear_viewport()
            self.query_bluetooth("")
        return False

    def _adapters(self) -> list[Any]:
        if self._client is not None and hasattr(self._client, "adapters"):
            adapters = self._client.adapters  # type: ignore
            if adapters:
                return list(adapters)  # type: ignore
        return []

    def _devices(self) -> list[tuple[Any, Any | None]]:
        if self._client is not None and hasattr(self._client, "devices"):
            devices = self._client.devices  # type: ignore
            if devices is not None:
                result: list[tuple[Any, Any | None]] = []
                for d in devices:
                    adapter = d.adapter if hasattr(d, "adapter") else None
                    result.append((d, adapter))
                return result
        return []

    def _enumerate(self, text: str) -> list[dict]:
        text = (text or "").strip().lower()
        items: list[dict] = []

        # First add power/scan controls per adapter
        for ad in self._adapters():
            if hasattr(ad, "Alias"):
                name = ad.Alias  # type: ignore
            elif hasattr(ad, "Name"):
                name = ad.Name  # type: ignore
            else:
                name = "Adapter"
            if hasattr(ad, "Powered"):
                powered = bool(ad.Powered)  # type: ignore
            elif hasattr(ad, "powered"):
                powered = bool(ad.powered)  # type: ignore
            else:
                powered = False
            if hasattr(ad, "Discovering"):
                discovering = bool(ad.Discovering)  # type: ignore
            elif hasattr(ad, "scanning"):
                discovering = bool(ad.scanning)  # type: ignore
            else:
                discovering = False
            items.append(
                {
                    "kind": "adapter",
                    "adapter": ad,
                    "name": f"{name}",
                    "subtitle": ("On" if powered else "Off")
                    + (" • Scanning" if discovering else ""),
                }
            )

        # Then add devices
        for dev, adapter in self._devices():
            if hasattr(dev, "Alias"):
                alias = dev.Alias  # type: ignore
            elif hasattr(dev, "Name"):
                alias = dev.Name  # type: ignore
            elif hasattr(dev, "name"):
                alias = dev.name  # type: ignore
            else:
                alias = "Unknown"
            if text and (alias.lower().find(text) < 0):
                continue
            if hasattr(dev, "Connected"):
                connected = bool(dev.Connected)  # type: ignore
            elif hasattr(dev, "connected"):
                connected = bool(dev.connected)  # type: ignore
            else:
                connected = False
            if hasattr(dev, "Paired"):
                paired = bool(dev.Paired)  # type: ignore
            elif hasattr(dev, "paired"):
                paired = bool(dev.paired)  # type: ignore
            else:
                paired = False
            if hasattr(dev, "Trusted"):
                trusted = bool(dev.Trusted)  # type: ignore
            elif hasattr(dev, "trusted"):
                trusted = bool(dev.trusted)  # type: ignore
            else:
                trusted = False
            icon = "bluetooth"
            subtitle_bits = []
            if adapter:
                if hasattr(adapter, "Alias") and adapter.Alias:  # type: ignore
                    subtitle_bits.append(adapter.Alias)  # type: ignore
                elif hasattr(adapter, "Name") and adapter.Name:  # type: ignore
                    subtitle_bits.append(adapter.Name)  # type: ignore
            if paired:
                subtitle_bits.append("Paired")
            if trusted:
                subtitle_bits.append("Trusted")
            if connected:
                subtitle_bits.append("Connected")
            items.append(
                {
                    "kind": "device",
                    "device": dev,
                    "name": alias,
                    "subtitle": " • ".join(subtitle_bits) or "",
                    "icon": icon,
                    "connected": connected,
                }
            )
        return items

    def _show_empty(self) -> None:
        self.handler.slot_ready(
            Button(
                style_classes="app-slot bluetooth-empty",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Image(icon_name="bluetooth-disabled-symbolic", size=32),
                        Label(
                            label="No Bluetooth items",
                            style_classes="bluetooth-empty-text",
                            h_align="center",
                        ),
                    ],
                ),
                tooltip_text="No Bluetooth adapters/devices",
            ),
            "bluetooth",
        )
        self.handler.done()

    def _show_no_results(self) -> None:
        self.handler.slot_ready(
            Button(
                style_classes="app-slot bluetooth-no-results",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Label(
                            label="No devices match your search",
                            style_classes="bluetooth-no-results-text",
                            h_align="center",
                        ),
                    ],
                ),
            ),
            "bluetooth",
        )
        self.handler.done()

    def _show_scanning_indicator(self) -> None:
        self.handler.slot_ready(
            Button(
                style_classes="app-slot bluetooth-scanning",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Image(icon_name="content-loading-symbolic", size=24),
                        Label(
                            label="Scanning for Bluetooth devices...",
                            style_classes="bluetooth-scanning-text",
                            h_align="center",
                        ),
                    ],
                ),
                tooltip_text="Scanning is in progress",
            ),
            "bluetooth",
        )

    def _show_error_message(self, message: str) -> None:
        self.handler.slot_ready(
            Button(
                style_classes="app-slot bluetooth-error",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Label(
                            label=message,
                            style_classes="bluetooth-error-text",
                            h_align="center",
                        ),
                    ],
                ),
                on_clicked=lambda *_: self.handler.launched(),
            ),
            "bluetooth",
        )
        self.handler.done()

    def _show_help(self) -> None:
        help_text = (
            "Available commands:\n"
            "• power on|off (Toggle if no arg)\n"
            "• scan start|stop (Toggle if no arg)\n"
            "• connect <device_name>\n"
            "• disconnect <device_name>\n"
        )
        self.handler.slot_ready(
            Button(
                style_classes="app-slot bluetooth-help",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Label(
                            label=help_text,
                            style_classes="bluetooth-help-text",
                            h_align="center",
                        ),
                    ],
                ),
                on_clicked=lambda *_: self.handler.launched(),
            ),
            "bluetooth",
        )
        self.handler.done()

    def _bake_next_slot(self, iterator: Iterator[dict]) -> bool:
        try:
            item = next(iterator)
        except StopIteration:
            idle_add(self.handler.done)
            return False
        self._create_slot(item)
        return True

    def _create_slot(self, item: dict) -> None:
        icon_name = item.get("icon") or (
            "bluetooth-active" if item.get("kind") == "device" else "bluetooth"
        )
        slot_content = Box(
            orientation="h",
            spacing=12,
            children=[
                Image(icon_name=icon_name, h_align="start", size=32),
                Box(
                    orientation="v",
                    children=[
                        Label(
                            label=item.get("name", "Unknown"),
                            style_classes="bluetooth-name",
                            h_align="start",
                            v_align="start",
                        ),
                        Label(
                            label=item.get("subtitle", ""),
                            style_classes="bluetooth-subtitle",
                            h_align="start",
                            v_align="start",
                        ),
                    ],
                ),
            ],
        )

        tooltip = (
            "Enter: Toggle Connect/Disconnect\nShift+Enter: Pair/Remove"
            if item.get("kind") == "device"
            else "Enter: Toggle Power\nShift+Enter: Scan"
        )

        self.handler.slot_ready(
            Button(
                style_classes="app-slot bluetooth-slot",
                child=slot_content,
                tooltip_text=tooltip,
                on_clicked=lambda *_: self._on_slot_click(item),
            ),
            "bluetooth",
        )
        self.current_slots.append({"widget": None, "item": item})

    def _on_slot_click(self, item: dict) -> None:
        kind = item.get("kind")
        if kind == "device":
            dev = item.get("device")
            if self._client is not None:
                if not item.get("connected") and hasattr(dev, "set_connecting"):
                    dev.set_connecting(True)  # type: ignore
                if hasattr(dev, "connected"):
                    dev.connected = not bool(item.get("connected"))  # type: ignore
            self.handler.launched()
            return
        if kind == "adapter":
            ad = item.get("adapter")
            if self._client is not None and hasattr(ad, "toggle_power"):
                ad.toggle_power()  # type: ignore
            else:
                current = bool(ad.powered) if hasattr(ad, "powered") else False
                if hasattr(ad, "powered"):
                    ad.powered = not current  # type: ignore
            self.handler.launched()

    def handle_external(self, command: str, args: str) -> None:
        # Map external command to internal logic
        # This is a simplified version of handle_direct
        # In a real scenario, we might want to reuse handle_direct logic
        pass

    def _btctl(self, subcommand: str) -> bool:
        try:
            cmd = shlex.split(f"bluetoothctl {subcommand}")
            result = run_command(cmd, timeout=5)
            return result.returncode == 0
        except Exception:
            return False

    def _handle_power_command(self, text: str) -> None:
        parts = text.strip()
        if not parts.endswith(";"):
            self._show_error_message(
                "Bluetooth: command must end with ';'\nUsage: power on; | power off;"
            )
            return
        parts = parts[:-1].strip()
        tokens = parts.split()
        state = tokens[1].lower() if len(tokens) > 1 else ""
        if self._client is not None and hasattr(self._client, "toggle_power"):
            if state:
                desired = state in ("on", "1", "true", "enable")
                self._client.enabled = desired  # type: ignore
            else:
                self._client.toggle_power()  # type: ignore
        else:
            if state in ("on", "1", "true", "enable"):
                self._btctl("power on")
            elif state in ("off", "0", "false", "disable"):
                self._btctl("power off")
            else:
                self._btctl("power off")
                self._btctl("power on")

    def _handle_scan_command(self, text: str) -> None:
        parts = text.strip()
        if not parts.endswith(";"):
            self._show_error_message(
                "Bluetooth: command must end with ';'\nUsage: scan start; | scan stop;"
            )
            return
        parts = parts[:-1].strip()
        tokens = parts.split()
        action = tokens[1].lower() if len(tokens) > 1 else ""
        if self._client is not None:
            if action in ("start", "on", "1") and hasattr(self._client, "scan"):
                self._client.scan()  # type: ignore
            elif action in ("stop", "off", "0"):
                self._client.scanning = False  # type: ignore
            elif hasattr(self._client, "toggle_scan"):
                self._client.toggle_scan()  # type: ignore

    def _handle_connect_command(self, text: str) -> None:
        parts = text.strip()
        if not parts.endswith(";"):
            self._show_error_message(
                "Bluetooth: command must end with ';'\nUsage: connect AA:BB:CC:DD:EE:FF;"
            )
            return
        parts = parts[:-1].strip()
        tokens = parts.split()
        if len(tokens) < 2:
            self._show_help()
            return
        name = " ".join(tokens[1:])
        if self._client is not None:
            self._with_device_by_name(
                name,
                lambda d: setattr(d, "connected", True)
                if hasattr(d, "connected")
                else None,
            )

    def _handle_disconnect_command(self, text: str) -> None:
        parts = text.strip()
        if not parts.endswith(";"):
            self._show_error_message(
                "Bluetooth: command must end with ';'\nUsage: disconnect AA:BB:CC:DD:EE:FF;"
            )
            return
        parts = parts[:-1].strip()
        tokens = parts.split()
        if len(tokens) < 2:
            self._show_help()
            return
        name = " ".join(tokens[1:])
        if self._client is not None:
            self._with_device_by_name(
                name,
                lambda d: setattr(d, "connected", False)
                if hasattr(d, "connected")
                else None,
            )

    def _with_device_by_name(self, name: str, op) -> bool:
        name_l = name.strip().lower()
        if self._client is None:
            return False
        devices = self._client.devices if hasattr(self._client, "devices") else []  # type: ignore
        for d in devices:
            alias = (
                d.Alias
                if hasattr(d, "Alias")
                else (
                    d.Name
                    if hasattr(d, "Name")
                    else (d.name if hasattr(d, "name") else "")
                )
            )  # type: ignore
            if str(alias).strip().lower() == name_l:
                op(d)
                return True
        return False
