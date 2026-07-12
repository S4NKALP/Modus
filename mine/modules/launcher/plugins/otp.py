import json
from collections.abc import Iterator
from pathlib import Path

from fabric.utils import Gdk, GLib, idle_add, remove_handler
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label

from config.data import plugins
from modules.launcher.base import LauncherPlugin
from services import (
    generate_totp,
    get_time_remaining,
    scan_qr_and_add_account,
    validate_base32_secret,
)
from utils.functions import copy_text, trigger_paste_shortcut


class OTPPlugin(LauncherPlugin):
    @property
    def name(self) -> str:
        return "otp"

    @property
    def icon(self) -> str:
        return "security-high-symbolic"

    @property
    def keywords(self) -> list[str]:
        return ["otp"]

    def __init__(self, handler):
        super().__init__(handler)
        self.secrets_file_path = Path(plugins) / "accounts.json"
        self.secrets_file_path.parent.mkdir(parents=True, exist_ok=True)

        self._query_handler: int = 0
        self._timer_handler: int = 0
        self.accounts: dict = {}
        self.current_slots: list = []
        self._load_accounts()

    def on_search(self, text: str) -> None:
        self.query_otp(text)

    def stop(self):
        if self._query_handler:
            remove_handler(self._query_handler)
            self._query_handler = 0
        if self._timer_handler:
            GLib.source_remove(self._timer_handler)
            self._timer_handler = 0
        self.current_slots.clear()

    def _load_accounts(self) -> None:
        self.accounts.clear()
        if not self.secrets_file_path.exists():
            return

        try:
            with open(self.secrets_file_path, encoding="utf-8") as f:
                self.accounts = json.load(f)
        except (OSError, json.JSONDecodeError):
            self.accounts = {}

    def _save_accounts(self) -> None:
        try:
            with open(self.secrets_file_path, "w", encoding="utf-8") as f:
                json.dump(self.accounts, f, indent=2)
        except OSError:
            pass

    def query_otp(self, text: str) -> None:
        self.handler.start("otp")
        self._load_accounts()

        self.current_slots.clear()
        if self._timer_handler:
            GLib.source_remove(self._timer_handler)
            self._timer_handler = 0

        immediate_commands = {
            "add": self._handle_add_command,
            "remove": self._handle_remove_command,
            "help": lambda t: self._show_command_help(),
        }

        for prefix, handler in immediate_commands.items():
            if text.strip().startswith(prefix):
                handler(text)
                return

        if not self.accounts:
            self._show_no_accounts()
            return

        filtered_accounts = self._filter_accounts(text)
        if not filtered_accounts:
            self._show_no_results()
            return

        self._query_handler = idle_add(
            self._bake_next_otp_slot, iter(filtered_accounts), pin=True
        )

    def _filter_accounts(self, text: str) -> Iterator[tuple[str, dict]]:
        if not text.strip():
            return iter(self.accounts.items())

        text_lower = text.lower()
        return iter(
            (name, data)
            for name, data in self.accounts.items()
            if text_lower in name.lower()
        )

    def _show_no_accounts(self) -> None:
        self.handler.slot_ready(
            Button(
                style_classes="app-slot otp-no-accounts",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Label(
                            label="No OTP accounts found",
                            style_classes="otp-no-accounts-text",
                            h_align="center",
                        ),
                    ],
                ),
                tooltip_text="Use 'add account_name qr' or 'add account_name secret_key' to add accounts",
            ),
            "otp",
        )
        self.handler.done()

    def _show_no_results(self) -> None:
        self.handler.slot_ready(
            Button(
                style_classes="app-slot otp-no-results",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Label(
                            label="No accounts match your search",
                            style_classes="otp-no-results-text",
                            h_align="center",
                        ),
                    ],
                ),
            ),
            "otp",
        )
        self.handler.done()

    def _bake_next_otp_slot(self, iterator: Iterator[tuple[str, dict]]) -> bool:
        try:
            account_name, account_data = next(iterator)
        except StopIteration:
            if self.current_slots:
                self._start_timer()
            idle_add(self.handler.done)
            return False

        self._create_otp_slot(account_name, account_data)
        return True

    def _create_otp_slot(self, account_name: str, account_data: dict) -> None:
        secret = account_data.get("secret", "")
        otp_code = generate_totp(secret)

        if not otp_code:
            return

        display_name = account_name
        time_remaining = get_time_remaining()

        timer_label = Label(
            label=f"{time_remaining}s",
            style_classes="otp-timer",
            h_align="end",
        )

        code_label = Label(
            label=otp_code,
            style_classes="otp-code",
            h_align="start",
        )

        name_label = Label(
            label=display_name,
            style_classes="otp-account-name",
            h_align="start",
            max_chars_width=35,
            ellipsization="end",
        )

        tooltip_text = "Click to copy OTP code"

        slot_widget = Button(
            style_classes="app-slot otp-slot",
            child=Box(
                orientation="v",
                spacing=4,
                children=[
                    name_label,
                    Box(
                        orientation="h",
                        spacing=8,
                        children=[
                            code_label,
                            timer_label,
                        ],
                    ),
                ],
            ),
            tooltip_text=tooltip_text,
            on_clicked=lambda *_: self._copy_otp_code(otp_code),
        )

        slot_widget.connect(
            "key-press-event",
            lambda widget, event, acc_name=account_name: self._on_slot_key_press(
                widget, event, acc_name
            ),
        )

        slot_info = {
            "widget": slot_widget,
            "timer_label": timer_label,
            "code_label": code_label,
            "account_name": account_name,
            "account_data": account_data,
        }
        self.current_slots.append(slot_info)
        self.handler.slot_ready(slot_widget, "otp")

    def _copy_otp_code(self, code: str) -> None:
        copy_text(code)
        self.handler.launched()
        GLib.timeout_add(5, lambda: (trigger_paste_shortcut(0), False)[1])

    def _on_slot_key_press(self, widget, event, account_name: str) -> bool:
        if not event:
            return False
        return (
            (event.keyval == Gdk.KEY_Return or event.keyval == Gdk.KEY_KP_Enter)
            and event.state & Gdk.ModifierType.SHIFT_MASK
            and (
                self.remove_account(account_name)
                and self._refresh_account_list()
                or True
            )
        )

    def add_account_manually(self, account_name: str, secret: str) -> bool:
        validation = validate_base32_secret(secret)
        if not validation["success"]:
            return False

        self.accounts[account_name] = {
            "secret": validation["secret"],
            "algorithm": "SHA1",
            "digits": 6,
            "period": 30,
        }
        self._save_accounts()
        return True

    def remove_account(self, account_name: str) -> bool:
        if account_name not in self.accounts:
            return False
        del self.accounts[account_name]
        self._save_accounts()
        return True

    def _start_timer(self) -> None:
        if self._timer_handler:
            GLib.source_remove(self._timer_handler)
        self._timer_handler = GLib.timeout_add_seconds(1, self._update_timers)

    def _update_timers(self) -> bool:
        if not self.current_slots:
            return False

        for slot_info in self.current_slots:
            secret = slot_info["account_data"].get("secret", "")
            otp_code = generate_totp(secret)
            if otp_code:
                slot_info["code_label"].set_text(otp_code)
            slot_info["timer_label"].set_text(f"{get_time_remaining()}s")
        return True

    def _refresh_account_list(self) -> None:
        self.current_slots.clear()
        if self._timer_handler:
            GLib.source_remove(self._timer_handler)
            self._timer_handler = 0

        if hasattr(self.handler, "clear_viewport"):
            self.handler.clear_viewport()

        self._load_accounts()
        idle_add(self._show_account_list)

    def _show_account_list(self) -> None:
        self.handler.start("otp")
        if not self.accounts:
            self._show_no_accounts()
            return

        filtered_accounts = self._filter_accounts("")
        if not filtered_accounts:
            self._show_no_results()
            return

        self._query_handler = idle_add(
            self._bake_next_otp_slot, iter(filtered_accounts), pin=True
        )

    def _handle_add_command(self, text: str) -> None:
        text_stripped = text.strip()
        parts = text_stripped.split()

        if len(parts) < 3:
            self._show_command_help("add")
            return

        account_name = parts[1]
        secret_or_qr = parts[2].rstrip(";")  # Remove semicolon if present

        if secret_or_qr.lower() == "qr":
            # QR code scanning doesn't require semicolon
            result = scan_qr_and_add_account(account_name, str(self.secrets_file_path))
            if not result["success"]:
                self._show_error_message(f"Error adding account: {result['error']}")
                return
        else:
            # Secret key must end with semicolon
            if not text_stripped.endswith(";"):
                self._show_error_message(
                    "Add command with secret key must end with ';'\n\nUsage: add account_name secret_key;"
                )
                return

            # Remove semicolon and extract secret key (handles spaces in secret)
            command_text = text_stripped[:-1]  # Remove semicolon
            # Split into max 3 parts: ["add", "account_name", "secret_key with spaces"]
            command_parts = command_text.split(None, 2)
            if len(command_parts) < 3:
                self._show_command_help("add")
                return

            account_name = command_parts[1]
            secret_key = command_parts[2]  # This will contain the entire secret key

            if not self.add_account_manually(account_name, secret_key):
                self._show_error_message(f"Failed to add account: {account_name}")
                return

        if hasattr(self.handler, "clear_input"):
            self.handler.clear_input()
        self._refresh_account_list()

    def _handle_remove_command(self, text: str) -> None:
        if text.strip() == "remove":
            self._show_account_list()
            return

        parts = text.strip().split()
        if len(parts) < 2:
            self._show_command_help("remove")
            return

        account_name = parts[1]
        if not self.remove_account(account_name):
            self._show_error_message(f"Account not found: {account_name}")
            return

        if hasattr(self.handler, "clear_input"):
            self.handler.clear_input()
        self._refresh_account_list()

    def _show_command_help(self, command: str = None) -> None:
        help_texts = {
            "add": "Usage: add account_name qr\nadd account_name secret_key;",
            "remove": "Usage: remove account_name",
        }

        help_text = help_texts.get(
            command,
            """Available commands:
• add account_name qr
• add account_name secret_key;
• remove account_name
• help
Click on any OTP code to copy it!""",
        )

        self.handler.slot_ready(
            Button(
                style_classes="app-slot otp-help",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Label(
                            label=help_text,
                            style_classes="otp-help-text",
                            h_align="center",
                        ),
                    ],
                ),
            ),
            "otp",
        )
        self.handler.done()

    def _show_error_message(self, message: str) -> None:
        self.handler.slot_ready(
            Button(
                style_classes="app-slot otp-error",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Label(
                            label=message,
                            style_classes="otp-error-text",
                            h_align="center",
                        ),
                    ],
                ),
                on_clicked=lambda *_: self.handler.launched(),
            ),
            "otp",
        )
        self.handler.done()

    def handle_external(self, command: str, args: str) -> None:
        # Map external commands if needed
        pass
