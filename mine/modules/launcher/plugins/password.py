from collections.abc import Iterator
from pathlib import Path

from fabric.utils import Gdk, GLib, idle_add, remove_handler
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label

from config.data import plugins
from modules.launcher.base import LauncherPlugin
from services import PasswordManager
from utils.functions import copy_text, trigger_paste_shortcut


class PasswordManagerPlugin(LauncherPlugin):
    @property
    def name(self) -> str:
        return "passwords"

    @property
    def icon(self) -> str:
        return "dialog-password-symbolic"

    @property
    def keywords(self) -> list[str]:
        return ["pass"]

    def __init__(self, handler):
        super().__init__(handler)
        self.passwords_dir = Path(plugins) / "passwords"
        self.passwords_dir.mkdir(parents=True, exist_ok=True)
        self.passwords_file_path = self.passwords_dir / "passwords.json"
        self.key_file_path = self.passwords_dir / "key.key"
        self.salt_file_path = self.passwords_dir / "salt.key"

        self._query_handler: int = 0
        self.current_slots: list = []
        self.passwords: dict = {}
        self.password_manager = None
        self.master_password_set = False
        self._awaiting_master_password: bool = False

    def on_search(self, text: str) -> None:
        self.query_passwords(text)

    def stop(self):
        if self._query_handler:
            remove_handler(self._query_handler)
            self._query_handler = 0
        self.current_slots.clear()

    @property
    def is_password_mode(self) -> bool:
        return self._awaiting_master_password

    def _is_unlocked(self) -> bool:
        return self.password_manager is not None and self.master_password_set

    def is_waiting_for_password(self) -> bool:
        return self._awaiting_master_password

    def _get_password_manager(self, master_password: str = None):
        if self.password_manager is None and master_password:
            self.password_manager = PasswordManager(master_password)
            self.password_manager.passwords_file = self.passwords_file_path
            self.password_manager.key_file = self.key_file_path
            self.password_manager.salt_file = self.salt_file_path
            self.password_manager._initialize_password_file()
            self.password_manager._setup_encryption()
            self.master_password_set = True
        return self.password_manager

    def _check_master_password_exists(self) -> bool:
        return self.key_file_path.exists()

    def _initialize_password_manager(self, password: str) -> bool:
        try:
            self.password_manager = PasswordManager(password)
            self.password_manager.passwords_file = self.passwords_file_path
            self.password_manager.key_file = self.key_file_path
            self.password_manager.salt_file = self.salt_file_path
            self.password_manager._initialize_password_file()
            self.password_manager._setup_encryption()
            self.master_password_set = True
            return True
        except Exception:
            return False

    def _verify_master_password(self, password: str) -> bool:
        try:
            temp_pm = PasswordManager(password)
            temp_pm.passwords_file = self.passwords_file_path
            temp_pm.key_file = self.key_file_path
            temp_pm.salt_file = self.salt_file_path
            temp_pm._initialize_password_file()
            temp_pm._setup_encryption()

            return temp_pm.verify_master_password(password)
        except Exception:
            return False

    def query_passwords(self, text: str) -> None:
        self.handler.start("passwords")
        self.current_slots.clear()
        text_stripped = text.strip()

        commands = {
            "lock": self._handle_lock_command,
            "help": lambda t: self._show_command_help(),
            "add": self._handle_add_command,
            "remove": self._handle_remove_command,
            "update": self._handle_update_command,
        }

        for prefix, handler in commands.items():
            if text_stripped.startswith(prefix):
                if (
                    prefix in ("add", "remove", "update")
                    and not self._is_unlocked()
                    and self._check_master_password_exists()
                ):
                    self._prompt_master_password()
                    return
                if prefix in ("add", "remove", "update") and not self._is_unlocked():
                    self._show_master_password_required()
                    return
                handler(text)
                return

        if not self._is_unlocked():
            if self._check_master_password_exists():
                self._prompt_master_password()
            else:
                self._prompt_master_password_for_setup()
            return
        self._load_and_display_passwords(text)

    def _load_and_display_passwords(self, text: str) -> None:
        pm = self._get_password_manager()
        if not pm:
            self._show_master_password_required()
            return

        result = pm.list_passwords(decrypt_passwords=False)
        if not result["success"]:
            self._show_error_message(f"Failed to load passwords: {result['error']}")
            return

        self.passwords = result["data"]
        # Remove the master password hash and salt from display
        self.passwords.pop("_master_password_hash", None)
        self.passwords.pop("_master_password_salt", None)

        if not self.passwords:
            self._show_no_passwords()
            return

        filtered_passwords = self._filter_passwords(text)
        if not filtered_passwords:
            self._show_no_results()
            return

        self._query_handler = idle_add(
            self._bake_next_password_slot, iter(filtered_passwords), pin=True
        )

    def _filter_passwords(self, text: str) -> Iterator[tuple[str, dict]]:
        if not text.strip():
            return iter(self.passwords.items())

        text_lower = text.lower()
        return iter(
            (name, data)
            for name, data in self.passwords.items()
            if (
                text_lower in name.lower()
                or text_lower in data.get("username", "").lower()
            )
        )

    def _show_no_passwords(self) -> None:
        self.handler.slot_ready(
            Button(
                style_classes="app-slot password-no-passwords",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Label(
                            label="No passwords found",
                            style_classes="password-no-passwords-text",
                            h_align="center",
                        ),
                    ],
                ),
                tooltip_text="Use 'add name username password' to add passwords",
            ),
            "passwords",
        )
        self.handler.done()

    def _show_no_results(self) -> None:
        self.handler.slot_ready(
            Button(
                style_classes="app-slot password-no-results",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Label(
                            label="No passwords match your search",
                            style_classes="password-no-results-text",
                            h_align="center",
                        ),
                    ],
                ),
            ),
            "passwords",
        )
        self.handler.done()

    def _bake_next_password_slot(self, iterator: Iterator[tuple[str, dict]]) -> bool:
        try:
            password_name, password_data = next(iterator)
        except StopIteration:
            idle_add(self.handler.done)
            return False

        self._create_password_slot(password_name, password_data)
        return True

    def _create_password_slot(self, password_name: str, password_data: dict) -> None:
        username = password_data.get("username", "")
        name_label = Label(
            label=password_name,
            style_classes="password-name",
            h_align="start",
            max_chars_width=25,
            ellipsization="end",
        )

        username_label = Label(
            label=username if username else "No username",
            style_classes="password-username",
            h_align="start",
            max_chars_width=30,
            ellipsization="end",
        )

        children = [name_label, username_label]

        slot_widget = Button(
            style_classes="app-slot password-slot",
            child=Box(
                orientation="v",
                spacing=4,
                children=children,
            ),
            tooltip_text="Click to copy password",
            on_clicked=lambda *_: self._copy_password(password_name),
        )

        slot_widget.connect(
            "key-press-event",
            lambda widget, event, pwd_name=password_name: self._on_slot_key_press(
                widget, event, pwd_name
            ),
        )

        slot_info = {
            "widget": slot_widget,
            "name_label": name_label,
            "username_label": username_label,
            "password_name": password_name,
            "password_data": password_data,
        }
        self.current_slots.append(slot_info)
        self.handler.slot_ready(slot_widget, "passwords")

    def _copy_password(self, password_name: str) -> None:
        pm = self._get_password_manager()
        if not pm:
            self._show_master_password_required()
            return

        result = pm.get_password(password_name, decrypt=True)
        if not result["success"]:
            self._show_error_message(f"Failed to get password: {result['error']}")
            return

        password = result["data"]["password"]
        copy_text(password)
        self.handler.launched()
        GLib.timeout_add(5, lambda: (trigger_paste_shortcut(0), False)[1])

    def _on_slot_key_press(self, widget, event, password_name: str) -> bool:
        if not event:
            return False
        return (
            (event.keyval == Gdk.KEY_Return or event.keyval == Gdk.KEY_KP_Enter)
            and event.state & Gdk.ModifierType.SHIFT_MASK
            and (self._handle_remove_command(f"remove {password_name};") or True)
        )

    def _prompt_master_password(self) -> None:
        self._awaiting_master_password = True
        self.handler.start("passwords")
        if hasattr(self.handler, "clear_viewport"):
            self.handler.clear_viewport()
        if hasattr(self.handler, "clear_input"):
            self.handler.clear_input()

        self.handler.slot_ready(
            Button(
                style_classes="app-slot password-help",
                child=Box(
                    orientation="v",
                    spacing=8,
                    children=[
                        Label(
                            label="Enter master password",
                            style_classes="password-help-text",
                            h_align="center",
                        ),
                        Label(
                            label="Enter=Submit • Empty=Cancel",
                            style_classes="password-help-subtext",
                            h_align="center",
                        ),
                    ],
                ),
            ),
            "passwords",
        )
        self.handler.done()

    def _prompt_master_password_for_setup(self) -> None:
        self._awaiting_master_password = True
        self.handler.start("passwords")
        if hasattr(self.handler, "clear_viewport"):
            self.handler.clear_viewport()
        if hasattr(self.handler, "clear_input"):
            self.handler.clear_input()

        self.handler.slot_ready(
            Button(
                style_classes="app-slot password-help",
                child=Box(
                    orientation="v",
                    spacing=8,
                    children=[
                        Label(
                            label="Set master password",
                            style_classes="password-help-text",
                            h_align="center",
                        ),
                        Label(
                            label="Enter=Submit • Empty=Cancel",
                            style_classes="password-help-subtext",
                            h_align="center",
                        ),
                    ],
                ),
            ),
            "passwords",
        )
        self.handler.done()

    def submit_password(self, password: str) -> None:
        if not self._awaiting_master_password:
            return
        if not password:
            self.cancel_password()
            return

        # Check if this is setup (no existing master password) or unlock (existing master password)
        if not self._check_master_password_exists():
            # Setup mode: initialize new master password
            if not self._initialize_password_manager(password):
                self._show_error_message("Failed to initialize password manager!")
                return
        else:
            # Unlock mode: verify existing master password
            if not self._verify_master_password(password):
                self._show_error_message("Invalid master password!")
                return
            if not self._initialize_password_manager(password):
                self._show_error_message("Failed to initialize password manager!")
                return

        self._awaiting_master_password = False
        if hasattr(self.handler, "clear_viewport"):
            self.handler.clear_viewport()
        self._refresh_password_list()

    def cancel_password(self) -> None:
        if not self._awaiting_master_password:
            return
        self._awaiting_master_password = False
        if hasattr(self.handler, "clear_viewport"):
            self.handler.clear_viewport()
        self._show_master_password_required()

    def reset_prompt_state(self) -> None:
        self._awaiting_master_password = False

    def _handle_lock_command(self, text: str) -> None:
        self.password_manager = None
        self.master_password_set = False
        self.current_slots.clear()

        if hasattr(self.handler, "clear_viewport"):
            self.handler.clear_viewport()
        if hasattr(self.handler, "clear_input"):
            self.handler.clear_input()
        self.handler.launched()

    def _handle_add_command(self, text: str) -> None:
        if not text.strip().endswith(";"):
            self._show_error_message(
                "Add command must end with ';'\n\nUsage: add name username password;"
            )
            return

        password_text = text.strip()[:-1]  # Remove semicolon
        parts = password_text.split(
            None, 3
        )  # Split into max 4 parts: ["add", "name", "username", "password with spaces"]
        if len(parts) < 4:
            self._show_command_help("add")
            return

        name = parts[1]
        username = parts[2]
        password = parts[
            3
        ]  # This will contain the entire password, even if it has spaces

        pm = self._get_password_manager()
        if not pm:
            self._show_master_password_required()
            return

        result = pm.add_password(name, username, password)
        if result["success"]:
            if hasattr(self.handler, "clear_input"):
                self.handler.clear_input()
            self._refresh_password_list()
        else:
            self._show_error_message(f"Error adding password: {result['error']}")

    def _handle_remove_command(self, text: str) -> None:
        if text.strip() == "remove":
            self._load_and_display_passwords("")
            return

        if not text.strip().endswith(";"):
            self._show_error_message(
                "Remove command must end with ';'\n\nUsage: remove name;"
            )
            return

        password_text = text.strip()[:-1]
        parts = password_text.split()
        if len(parts) < 2:
            self._show_command_help("remove")
            return

        password_name = parts[1]
        pm = self._get_password_manager()
        if not pm:
            self._show_master_password_required()
            return

        result = pm.delete_password(password_name)
        if not result["success"]:
            self._show_error_message(f"Error removing password: {result['error']}")
            return

        if hasattr(self.handler, "clear_input"):
            self.handler.clear_input()
        self._refresh_password_list()

    def _handle_update_command(self, text: str) -> None:
        if text.strip() == "update":
            self._load_and_display_passwords("")
            return

        if not text.strip().endswith(";"):
            self._show_error_message(
                "Update command must end with ';'\n\nUsage: update name field new_value;"
            )
            return

        password_text = text.strip()[:-1]
        parts = password_text.split()
        if len(parts) < 4:
            self._show_command_help("update")
            return

        password_name = parts[1]
        field = parts[2]

        if field not in ["username", "password"]:
            self._show_error_message("Invalid field. Use: username or password")
            return

        new_value = " ".join(parts[3:])
        pm = self._get_password_manager()
        if not pm:
            self._show_master_password_required()
            return

        result = pm.update_password(password_name, **{field: new_value})
        if not result["success"]:
            self._show_error_message(f"Error updating password: {result['error']}")
            return

        if hasattr(self.handler, "clear_input"):
            self.handler.clear_input()
        self._refresh_password_list()

    def _show_master_password_required(self) -> None:
        self.handler.slot_ready(
            Button(
                style_classes="app-slot password-master-required",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Label(
                            label="Master password required!\n\nYou'll be prompted to set a master password on first use, or to unlock if already set.",
                            style_classes="password-master-required-text",
                            h_align="center",
                        ),
                    ],
                ),
                tooltip_text="Set a master password to encrypt your passwords",
            ),
            "passwords",
        )
        self.handler.done()

    def _show_command_help(self, command: str = None) -> None:
        help_texts = {
            "add": "Usage: add name username password;\nExample: add gmail user@gmail.com mypass;\nNote: Must end with semicolon (;)",
            "remove": "Usage: remove name;\nExample: remove gmail;\nNote: Must end with semicolon (;)",
            "update": "Usage: update name field new_value;\nFields: username, password\nExample: update gmail password newpass123;\nNote: Must end with semicolon (;)",
            "lock": "Usage: lock\nExample: lock\n\nThis locks your password vault for security.\nYou'll need to enter the master password in the prompt when requested.",
        }

        help_text = help_texts.get(
            command,
            """Available commands:
• lock (LOCK VAULT FOR SECURITY!)
• add name username password;
• remove name;
• update name field new_value;
• help""",
        )

        self.handler.slot_ready(
            Button(
                style_classes="app-slot password-help",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Label(
                            label=help_text,
                            style_classes="password-help-text",
                            h_align="center",
                        ),
                    ],
                ),
            ),
            "passwords",
        )
        self.handler.done()

    def _show_error_message(self, message: str) -> None:
        self.handler.slot_ready(
            Button(
                style_classes="app-slot password-error",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Label(
                            label=message,
                            style_classes="password-error-text",
                            h_align="center",
                        ),
                    ],
                ),
                on_clicked=lambda *_: self.handler.launched(),
            ),
            "passwords",
        )
        self.handler.done()

    def _refresh_password_list(self) -> None:
        self.current_slots.clear()
        if hasattr(self.handler, "clear_viewport"):
            self.handler.clear_viewport()
        idle_add(self._show_password_list)

    def _show_password_list(self) -> None:
        self.handler.start("passwords")
        self._load_and_display_passwords("")

    def handle_external(self, command: str, args: str) -> None:
        # Map external commands if needed
        pass
