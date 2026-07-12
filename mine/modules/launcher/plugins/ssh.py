from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from fabric.utils import (
    Gdk,
    exec_shell_command_async,
    idle_add,
    os,
    re,
    remove_handler,
)
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label

from modules.launcher.base import LauncherPlugin
from utils.functions import copy_text, terminal_exec_command


class SSHPlugin(LauncherPlugin):
    @property
    def name(self) -> str:
        return "ssh"

    @property
    def icon(self) -> str:
        return "network-server-symbolic"

    @property
    def keywords(self) -> list[str]:
        return ["ssh"]

    def __init__(self, handler):
        super().__init__(handler)
        self._query_handler: int = 0
        self.current_slots: list = []
        self.terminal = "kitty"  # default terminal

        self._hosts_cache: list[dict] = []
        self._hosts_cache_hash: int | None = None

    def on_search(self, text: str) -> None:
        self.query_ssh(text)

    def stop(self):
        if self._query_handler:
            remove_handler(self._query_handler)
            self._query_handler = 0
        self.current_slots.clear()

    def query_ssh(self, text: str) -> None:
        self.handler.start("ssh")
        self.current_slots.clear()
        s = text.strip()

        commands = {
            "terminal": self._handle_terminal_command,
            "help": lambda t: self._show_command_help(),
        }

        for prefix, handler in commands.items():
            if s.startswith(prefix):
                handler(text)
                return

        self._load_and_display_hosts(text)

    def _load_and_display_hosts(self, text: str) -> None:
        hosts = self._load_hosts()
        if not hosts:
            self._show_no_hosts()
            return

        filtered = self._filter_hosts(text, hosts)
        # Convert to list to check if empty
        filtered_list = list(filtered)
        if not filtered_list:
            self._show_no_results()
            return

        self._query_handler = idle_add(
            self._bake_next_slot, iter(filtered_list), pin=True
        )

    def _filter_hosts(self, text: str, hosts: list[dict]) -> Iterator[dict]:
        if not text.strip():
            return iter(hosts)
        q = text.lower()
        return iter(
            h
            for h in hosts
            if q in h["name"].lower()
            or (h.get("user") and q in h["user"].lower())
            or (h.get("hostname") and q in h["hostname"].lower())
        )

    def _bake_next_slot(self, iterator: Iterator[dict]) -> bool:
        try:
            host = next(iterator)
        except StopIteration:
            idle_add(self.handler.done)
            return False
        self._create_slot(host)
        return True

    def _create_slot(self, host: dict) -> None:
        display = host["name"]
        subtitle = " · ".join(
            list(
                filter(
                    None,
                    [
                        host.get("user"),
                        host.get("hostname")
                        if host.get("hostname") != display
                        else None,
                    ],
                )
            )
        )

        name_label = Label(
            label=display,
            style_classes="ssh-host-name",
            h_align="start",
            max_chars_width=35,
            ellipsization="end",
        )

        info_label = Label(
            label=subtitle or "",
            style_classes="ssh-host-info",
            h_align="start",
            max_chars_width=40,
            ellipsization="end",
        )

        slot_widget = Button(
            style_classes="app-slot ssh-slot",
            child=Box(
                orientation="v",
                spacing=4,
                children=[name_label, info_label],
            ),
            on_clicked=lambda *_: self._connect(host),
            tooltip_text=(
                f"Enter: connect via {self.terminal}\nShift+Enter: copy ssh command"
            ),
        )

        slot_widget.connect(
            "key-press-event",
            lambda widget, event, h=host: self._on_slot_key_press(widget, event, h),
        )

        self.current_slots.append({"widget": slot_widget, "host": host})
        self.handler.slot_ready(slot_widget, "ssh")

    def _on_slot_key_press(self, widget, event, host: dict) -> bool:
        if not event:
            return False
        return bool(
            (event.keyval == Gdk.KEY_Return or event.keyval == Gdk.KEY_KP_Enter)
            and event.state & Gdk.ModifierType.SHIFT_MASK
            and not self._copy_command(host)
        )

    def _copy_command(self, host: dict) -> None:
        cmd = self._build_ssh_command(host)
        copy_text(cmd)
        self.handler.launched()

    def _connect(self, host: dict) -> None:
        cmd = self._build_ssh_command(host)
        term_cmd = self._terminal_command(cmd)
        exec_shell_command_async(term_cmd)
        self.handler.launched()

    def _terminal_command(self, inner_cmd: str) -> str:
        return terminal_exec_command(self.terminal, inner_cmd)

    def _build_ssh_command(self, host: dict) -> str:
        user = host.get("user")
        name = host["name"]
        return f"ssh {user}@{name}" if user else f"ssh {name}"

    def _show_no_hosts(self) -> None:
        self.handler.slot_ready(
            Button(
                style_classes="app-slot ssh-no-hosts",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Label(
                            label=(
                                "No SSH hosts found. Add entries to ~/.ssh/config or connect once to populate known_hosts."
                            ),
                            style_classes="ssh-no-hosts-text",
                            h_align="center",
                        ),
                    ],
                ),
            ),
            "ssh",
        )
        self.handler.done()

    def _show_error_message(self, message: str) -> None:
        self.handler.slot_ready(
            Button(
                style_classes="app-slot ssh-error",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Label(
                            label=message,
                            style_classes="ssh-error-text",
                            h_align="center",
                        ),
                    ],
                ),
                on_clicked=lambda *_: self.handler.launched(),
            ),
            "ssh",
        )
        self.handler.done()

    def _show_no_results(self) -> None:
        self.handler.slot_ready(
            Button(
                style_classes="app-slot ssh-no-results",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Label(
                            label="No SSH hosts match your search",
                            style_classes="ssh-no-results-text",
                            h_align="center",
                        ),
                    ],
                ),
            ),
            "ssh",
        )
        self.handler.done()

    def _handle_terminal_command(self, text: str) -> None:
        parts = text.strip().split()
        if len(parts) < 2:
            self._show_command_help("terminal")
            return
        self.terminal = parts[1]
        # show refreshed list after changing terminal
        self._refresh_host_list()

    def _show_command_help(self, command: str | None = None) -> None:
        help_texts = {
            "terminal": "Usage: terminal terminal_name\nExample: terminal kitty",
        }
        help_text = help_texts.get(
            command,
            """Available commands:
• terminal terminal_name (Set terminal emulator)
• help

Enter: connect via terminal
Shift+Enter: copy ssh command
""",
        )

        self.handler.slot_ready(
            Button(
                style_classes="app-slot ssh-help",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Label(
                            label=help_text,
                            style_classes="ssh-help-text",
                            h_align="center",
                        ),
                    ],
                ),
            ),
            "ssh",
        )
        self.handler.done()

    def _refresh_host_list(self) -> None:
        self.current_slots.clear()
        if hasattr(self.handler, "clear_viewport"):
            self.handler.clear_viewport()
        idle_add(self._show_host_list)

    def _show_host_list(self) -> None:
        self.handler.start("ssh")
        self._load_and_display_hosts("")

    def _load_hosts(self) -> list[dict]:
        user_config_path = Path(os.path.expanduser("~/.ssh/config"))
        system_config_paths = [
            Path("/etc/ssh/config"),
            Path("/etc/ssh/ssh_config"),
        ]
        known_hosts_path = Path(os.path.expanduser("~/.ssh/known_hosts"))

        cfg_mtime = self._stat_ns(user_config_path)
        sys_mtime_total = 0
        for p in system_config_paths:
            sys_mtime_total ^= self._stat_ns(p)
        kh_mtime = self._stat_ns(known_hosts_path)
        fingerprint = cfg_mtime ^ kh_mtime ^ sys_mtime_total
        if self._hosts_cache_hash == fingerprint and self._hosts_cache:
            return self._hosts_cache

        hosts_by_name: dict[str, dict] = {}

        for sys_cfg in system_config_paths:
            self._parse_ssh_config_content(
                self._read_text(sys_cfg),
                "system_config",
                hosts_by_name,
                overwrite=False,
            )

        self._parse_ssh_config_content(
            self._read_text(user_config_path),
            "user_config",
            hosts_by_name,
            overwrite=True,
        )

        self._parse_known_hosts(self._read_text(known_hosts_path), hosts_by_name)
        hosts = list(hosts_by_name.values())
        rank = {"user_config": 0, "system_config": 1}
        hosts.sort(key=lambda h: (rank.get(h.get("source"), 2), h["name"].lower()))

        self._hosts_cache = hosts
        self._hosts_cache_hash = fingerprint
        return hosts

    def _stat_ns(self, path: Path) -> int:
        return path.stat().st_mtime_ns if path.exists() else 0

    def _read_text(self, path: Path) -> str:
        return path.read_text() if path.exists() else ""

    def _parse_ssh_config_content(
        self,
        content: str,
        source: str,
        hosts_by_name: dict[str, dict],
        overwrite: bool,
    ) -> None:
        if not content:
            return
        blocks = re.split(r"\n(?=Host\s)", content, flags=re.IGNORECASE)
        for block in blocks:
            lines = [
                ln
                for ln in block.strip().splitlines()
                if ln.strip() and not ln.strip().startswith("#")
            ]
            if not lines:
                continue
            header = lines[0]
            m = re.match(r"Host\s+(.+)$", header, re.I)
            if not m:
                continue
            names = [n for n in m.group(1).split() if n != "*"]
            if not names:
                continue
            attrs = {}
            for ln in lines[1:]:
                parts = ln.split(None, 1)
                if len(parts) != 2:
                    continue
                key, val = parts[0].lower(), parts[1].strip()
                if key in ("user", "hostname"):
                    attrs[key] = val
            for name in names:
                if not overwrite and name in hosts_by_name:
                    continue
                hosts_by_name[name] = {
                    "name": name,
                    "user": attrs.get("user"),
                    "hostname": attrs.get("hostname", name),
                    "source": source,
                }

    def _parse_known_hosts(self, content: str, hosts_by_name: dict[str, dict]) -> None:
        if not content:
            return
        for line in content.splitlines():
            line_s = line.strip()
            if not line_s or line_s.startswith("#"):
                continue
            first = line_s.split()[0]
            if first.startswith("|"):
                continue  # hashed name
            for hostpart in first.split(","):
                host_clean = hostpart.strip()
                if host_clean and host_clean not in hosts_by_name:
                    hosts_by_name[host_clean] = {
                        "name": host_clean,
                        "user": None,
                        "hostname": host_clean,
                        "source": "known_hosts",
                    }

    def handle_external(self, command: str, args: str) -> None:
        # Map external commands if needed
        pass
