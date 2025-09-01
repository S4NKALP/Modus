import json
import subprocess
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from fabric.utils import get_relative_path
from modules.launcher.plugin_base import PluginBase
from modules.launcher.result import Result
from services.auth import (
    generate_totp,
    get_time_remaining_with_blink,
    parse_otpauth_uri,
    scan_qr_and_add_account,
    validate_base32_secret,
)


class OTPPlugin(PluginBase):
    """Plugin for managing TOTP (Time-based One-Time Password) codes."""

    def __init__(self):
        super().__init__()
        self.display_name = "OTP Manager"
        self.description = "Manage TOTP codes and 2FA authentication"

        self.secrets_file = Path(
            get_relative_path("../../../config/assets/accounts.json")
        )
        self.secrets: Dict[str, Dict] = {}
        self.last_update = 0

        # Threading for auto-refresh
        self.refresh_thread = None
        self.stop_refresh = threading.Event()

    def initialize(self):
        """Initialize the OTP plugin."""
        self.set_triggers(["otp"])
        self._load_secrets()
        self._ensure_config_file()
        self._start_refresh_thread()

    def cleanup(self):
        """Cleanup the OTP plugin."""
        if self.refresh_thread and self.refresh_thread.is_alive():
            self.stop_refresh.set()
            self.refresh_thread.join(timeout=1)

    def _load_secrets(self):
        """Load secrets from JSON file."""
        try:
            if self.secrets_file.exists():
                with open(self.secrets_file, "r", encoding="utf-8") as f:
                    self.secrets = json.load(f)
            else:
                self.secrets = {}
        except Exception as e:
            print(f"Error loading OTP secrets: {e}")
            self.secrets = {}

    def _save_secrets(self):
        """Save secrets to JSON file."""
        try:
            self.secrets_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.secrets_file, "w", encoding="utf-8") as f:
                json.dump(self.secrets, f, indent=2)
        except Exception as e:
            print(f"Error saving OTP secrets: {e}")

    def _ensure_config_file(self):
        """Ensure the config file exists."""
        if not self.secrets_file.exists():
            self.secrets_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.secrets_file, "w", encoding="utf-8") as f:
                json.dump({}, f, indent=2)

    def _start_refresh_thread(self):
        """Start background thread for auto-refreshing tokens."""

        def refresh_loop():
            while not self.stop_refresh.wait(5):
                current_time = time.time()
                if current_time - self.last_update >= 5:
                    self.last_update = current_time
                    # Only refresh if we have secrets and launcher is likely active
                    if self.secrets:
                        try:
                            self._selective_force_refresh()
                        except Exception:
                            pass

        self.refresh_thread = threading.Thread(target=refresh_loop, daemon=True)
        self.refresh_thread.start()

    def _selective_force_refresh(self):
        """Update time display in existing OTP result items."""
        try:
            import gc

            from gi.repository import GLib

            def do_update():
                try:
                    for obj in gc.get_objects():
                        if (
                            hasattr(obj, "__class__")
                            and obj.__class__.__name__ == "Launcher"
                            and hasattr(obj, "results_box")
                            and hasattr(obj, "visible")
                            and obj.visible
                            and hasattr(obj, "results")
                            and obj.results
                        ):
                            has_otp_results = any(
                                result.data and result.data.get("type") == "totp"
                                for result in obj.results
                                if hasattr(result, "data") and result.data
                            )

                            if has_otp_results:
                                self._update_existing_result_labels(obj.results_box)
                                return False
                except Exception:
                    pass
                return False

            GLib.idle_add(do_update)
        except Exception:
            pass

    def _update_existing_result_labels(self, results_box):
        """Update subtitle labels in existing ResultItem widgets."""
        try:
            time_display = self._get_time_remaining_with_blink()
            for child in results_box.get_children():
                if (
                    hasattr(child, "__class__")
                    and child.__class__.__name__ == "ResultItem"
                    and hasattr(child, "result")
                    and hasattr(child.result, "data")
                    and child.result.data
                    and child.result.data.get("type") == "totp"
                ):
                    self._update_result_item_content(child, time_display)
        except Exception as e:
            print(f"Error updating result labels: {e}")

    def _update_result_item_content(self, result_item, time_display):
        """Update both the title (OTP code) and subtitle (time display) of a specific ResultItem."""
        try:
            account_name = result_item.result.data.get("account", "")
            if not account_name or account_name not in self.secrets:
                return

            account_data = self.secrets[account_name]
            secret = account_data.get("secret", "")
            issuer = account_data.get("issuer", "")
            display_name = f"{issuer} - {account_name}" if issuer else account_name

            current_totp_code = self._generate_totp(secret)
            if not current_totp_code:
                return

            old_code = result_item.result.data.get("code", "")
            if current_totp_code != old_code:
                result_item.result.data["code"] = current_totp_code
                self._find_and_update_title_label(result_item, current_totp_code)
                result_item.result.action = (
                    lambda code=current_totp_code: self._copy_to_clipboard(code)
                )

            new_subtitle_markup = f"{display_name} • {time_display} remaining"
            self._find_and_update_subtitle_label(result_item, new_subtitle_markup)
        except Exception as e:
            print(f"Error updating result item: {e}")

    def _find_and_update_title_label(self, result_item, new_title):
        """Find the title label widget and update its text."""

        def find_title_label(widget):
            if hasattr(widget, "get_name") and widget.get_name() == "result-item-title":
                return widget
            if hasattr(widget, "get_children"):
                for child in widget.get_children():
                    found = find_title_label(child)
                    if found:
                        return found
            return None

        title_label = find_title_label(result_item)
        if title_label and hasattr(title_label, "set_label"):
            title_label.set_label(new_title)

    def _find_and_update_subtitle_label(self, result_item, new_markup):
        """Find the subtitle label widget and update its markup."""

        def find_subtitle_label(widget):
            if (
                hasattr(widget, "get_name")
                and widget.get_name() == "result-item-subtitle"
            ):
                return widget
            if hasattr(widget, "get_children"):
                for child in widget.get_children():
                    found = find_subtitle_label(child)
                    if found:
                        return found
            return None

        subtitle_label = find_subtitle_label(result_item)
        if subtitle_label and hasattr(subtitle_label, "set_markup"):
            subtitle_label.set_markup(new_markup)

    def _copy_to_clipboard(self, text: str):
        """Copy text to clipboard."""
        try:
            try:
                subprocess.run(["wl-copy"], input=text.encode(), check=True)
            except subprocess.SubprocessError:
                subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=text.encode(),
                    check=True,
                )
        except Exception as e:
            print(f"Failed to copy to clipboard: {e}")

    def _trigger_refresh(self):
        """Trigger launcher refresh to return to default OTP view."""
        try:
            from gi.repository import GLib

            # Use a small delay to ensure the action completes first
            def trigger_refresh():
                try:
                    # Try to access the launcher through the fabric Application
                    from fabric import Application

                    app = Application.get_default()

                    if app and hasattr(app, "launcher"):
                        launcher = app.launcher
                        if launcher and hasattr(launcher, "search_entry"):
                            # Clear the search entry and set it to just "otp "
                            launcher.search_entry.set_text("otp ")
                            # Position cursor at the end
                            launcher.search_entry.set_position(-1)
                            # Trigger the search to show default OTP view
                            if hasattr(launcher, "_perform_search"):
                                launcher._perform_search("otp ")
                            return False

                    # Fallback: try to find launcher instance through other means
                    import gc

                    for obj in gc.get_objects():
                        if (
                            hasattr(obj, "__class__")
                            and obj.__class__.__name__ == "Launcher"
                        ):
                            if hasattr(obj, "search_entry") and hasattr(
                                obj, "_perform_search"
                            ):
                                obj.search_entry.set_text("otp ")
                                obj.search_entry.set_position(-1)
                                obj._perform_search("otp ")
                                return False

                except Exception as e:
                    print(f"Error forcing launcher refresh: {e}")

                return False  # Don't repeat

            # Use a small delay to ensure the action completes first
            GLib.timeout_add(50, trigger_refresh)

        except Exception as e:
            print(f"Could not trigger refresh: {e}")

    def _remove_account_and_refresh(self, account_name: str):
        """Remove an account and trigger refresh to return to default OTP view."""
        try:
            if account_name in self.secrets:
                # Remove the account
                del self.secrets[account_name]
                self._save_secrets()

                # Trigger refresh to return to default OTP view
                self._trigger_refresh()
        except Exception as e:
            print(f"Error removing account {account_name}: {e}")

    def _generate_totp(self, secret: str) -> Optional[str]:
        """Generate TOTP code from secret."""
        return generate_totp(secret)

    def _get_time_remaining_with_blink(self) -> str:
        """Get time remaining with blinking effect."""
        return get_time_remaining_with_blink()

    def query(self, query_string: str) -> List[Result]:
        """Process OTP queries."""
        query = query_string.strip()

        if not query:
            return self._list_otp_codes()

        query_lower = query.lower()
        if query_lower.startswith("add "):
            add_content = query[4:].strip()

            # Handle both formats: with ``` and without ```
            if "```" in add_content:
                # Old format: add account```secret```
                parts = add_content.split("```", 1)
                if len(parts) == 2:
                    account_name = parts[0].strip()
                    secret_or_uri = parts[1].strip()
                    return self._handle_direct_add(account_name, secret_or_uri)
            elif " " in add_content:
                # New format: add account secret
                parts = add_content.split(" ", 1)
                if len(parts) == 2:
                    account_name = parts[0].strip()
                    secret_or_uri = parts[1].strip()
                    return self._handle_direct_add(account_name, secret_or_uri)

            return self._handle_add_command(add_content)
        elif query_lower == "remove" or query_lower.startswith("remove "):
            # Handle both "remove" and "remove accountname"
            if query_lower == "remove":
                remove_content = ""
            else:
                remove_content = query[7:].strip()
            return self._handle_remove_command(remove_content)
        elif query_lower == "qr" or query_lower.startswith("qr "):
            # Handle QR scanning command
            if query_lower == "qr":
                qr_content = ""
            else:
                qr_content = query[3:].strip()
            return self._handle_qr_command(qr_content)
        else:
            return self._search_accounts(query)

    def _handle_direct_add(self, account_name: str, secret_or_uri: str) -> List[Result]:
        """Handle direct addition of OTP account."""
        if not account_name or not secret_or_uri:
            return [
                Result(
                    title="Invalid format",
                    subtitle="Usage: add <account_name> <secret> or add <account_name>```<secret>```",
                    icon_name="info",
                    action=lambda: None,
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={"type": "help", "keep_launcher_open": True},
                )
            ]

        try:
            if secret_or_uri.startswith("otpauth://"):
                return self._handle_otpauth_uri(account_name, secret_or_uri)
            else:
                return self._handle_base32_secret(account_name, secret_or_uri)
        except Exception as e:
            print(f"OTP Debug: Error in _handle_direct_add: {e}")
            return [
                Result(
                    title="Error adding account",
                    subtitle=f"Debug: {str(e)}",
                    icon_name="cancel",
                    action=lambda: None,
                    relevance=0.5,
                    plugin_name=self.display_name,
                    data={"type": "error", "keep_launcher_open": True},
                )
            ]

    def _list_otp_codes(self) -> List[Result]:
        """List all OTP codes with current tokens."""
        results = []

        if not self.secrets:
            results.append(
                Result(
                    title="No OTP accounts configured",
                    subtitle="Use 'add <account> <secret>' to add your first account",
                    icon_name="gtk-authentication-symbolic",
                    action=lambda: None,
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={"type": "empty", "keep_launcher_open": True},
                )
            )
            results.append(
                Result(
                    title="Available commands:",
                    subtitle="add <account> <secret> | remove <account> | qr <account>",
                    icon_name="info",
                    action=lambda: None,
                    relevance=0.9,
                    plugin_name=self.display_name,
                    data={"type": "help", "keep_launcher_open": True},
                )
            )
            return results

        time_display = self._get_time_remaining_with_blink()

        for account_name, account_data in self.secrets.items():
            secret = account_data.get("secret", "")
            issuer = account_data.get("issuer", "")
            totp_code = self._generate_totp(secret)

            if totp_code:
                display_name = f"{issuer} - {account_name}" if issuer else account_name
                results.append(
                    Result(
                        title=f"{totp_code}",
                        subtitle_markup=f"{display_name} • {
                            time_display
                        } remaining • Shift+Enter: remove",
                        icon_name="gtk-authentication-symbolic",
                        action=lambda code=totp_code: self._copy_to_clipboard(code),
                        relevance=1.0,
                        plugin_name=self.display_name,
                        data={
                            "type": "totp",
                            "account": account_name,
                            "code": totp_code,
                            "alt_action": lambda acc=account_name: self._remove_account_and_refresh(
                                acc
                            ),
                        },
                    )
                )
            else:
                results.append(
                    Result(
                        title=f"Error: {account_name}",
                        subtitle="Invalid secret or configuration",
                        icon_name="dialog-cancel-symbolic",
                        action=lambda: None,
                        relevance=0.5,
                        plugin_name=self.display_name,
                        data={
                            "type": "error",
                            "account": account_name,
                            "keep_launcher_open": True,
                        },
                    )
                )

        return results

    def _search_accounts(self, query: str) -> List[Result]:
        """Search accounts by name or issuer."""
        results = []
        query_lower = query.lower()

        for account_name, account_data in self.secrets.items():
            issuer = account_data.get("issuer", "").lower()
            account_lower = account_name.lower()

            if query_lower in account_lower or query_lower in issuer:
                secret = account_data.get("secret", "")
                totp_code = self._generate_totp(secret)

                if totp_code:
                    display_name = (
                        f"{account_data.get('issuer', '')} - {account_name}"
                        if account_data.get("issuer")
                        else account_name
                    )
                    time_display = self._get_time_remaining_with_blink()

                    results.append(
                        Result(
                            title=f"{totp_code}",
                            subtitle_markup=f"{display_name} • {
                                time_display
                            } remaining • Shift+Enter: remove",
                            icon_name="gtk-authentication-symbolic",
                            action=lambda code=totp_code: self._copy_to_clipboard(code),
                            relevance=1.0,
                            plugin_name=self.display_name,
                            data={
                                "type": "totp",
                                "account": account_name,
                                "code": totp_code,
                                "alt_action": lambda acc=account_name: self._remove_account_and_refresh(
                                    acc
                                ),
                            },
                        )
                    )

        if not results:
            results.append(
                Result(
                    title=f"No accounts found for '{query}'",
                    subtitle="Use 'add <account> <secret>' to create new account",
                    icon_name="edit-find-symbolic",
                    action=lambda: None,
                    relevance=0.5,
                    plugin_name=self.display_name,
                    data={"type": "no_results", "keep_launcher_open": True},
                )
            )
            results.append(
                Result(
                    title="Available commands:",
                    subtitle="add <account> <secret> | remove <account> | qr <account>",
                    icon_name="info",
                    action=lambda: None,
                    relevance=0.4,
                    plugin_name=self.display_name,
                    data={"type": "help", "keep_launcher_open": True},
                )
            )

        return results

    def _handle_add_command(self, account_name: str) -> List[Result]:
        """Handle manual addition of OTP secret."""
        if not account_name:
            return [
                Result(
                    title="Enter account name",
                    subtitle="Usage: add <account_name> <secret>",
                    icon_name="dialog-question-symbolic",
                    action=lambda: None,
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={"type": "help", "keep_launcher_open": True},
                )
            ]

        return [
            Result(
                title=f"To add '{account_name}':",
                subtitle=f"Type: add {account_name} <secret>",
                icon_name="info",
                action=lambda: None,
                relevance=1.0,
                plugin_name=self.display_name,
                data={
                    "type": "instruction",
                    "account": account_name,
                    "keep_launcher_open": True,
                },
            ),
            Result(
                title="Base32 Secret Format:",
                subtitle="Example: add gmail JBSWY3DPEHPK3PXP",
                icon_name="info",
                action=lambda: None,
                relevance=0.9,
                plugin_name=self.display_name,
                data={"type": "help", "keep_launcher_open": True},
            ),
            Result(
                title="otpauth URI Format:",
                subtitle="Example: add github otpauth://totp/GitHub:user?secret=JBSWY3DPEHPK3PXP",
                icon_name="info",
                action=lambda: None,
                relevance=0.9,
                plugin_name=self.display_name,
                data={"type": "help", "keep_launcher_open": True},
            ),
            Result(
                title="Remove Account:",
                subtitle="Example: remove gmail",
                icon_name="trash",
                action=lambda: None,
                relevance=0.8,
                plugin_name=self.display_name,
                data={"type": "help", "keep_launcher_open": True},
            ),
        ]

    def _handle_qr_command(self, account_name: str) -> List[Result]:
        """Handle QR scanning command."""
        if not account_name:
            return [
                Result(
                    title="Scan QR Code",
                    subtitle="Click to scan QR code from screen",
                    icon_name="view-barcode-qr-symbolic",
                    action=lambda: self._scan_qr_and_add_account(""),
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={"type": "qr_scan"},
                ),
                Result(
                    title="QR Scan Instructions:",
                    subtitle="Use 'qr <account_name>' to specify account name",
                    icon_name="info",
                    action=lambda: None,
                    relevance=0.9,
                    plugin_name=self.display_name,
                    data={"type": "help", "keep_launcher_open": True},
                ),
            ]
        else:
            return [
                Result(
                    title=f"Scan QR Code for '{account_name}'",
                    subtitle="Click to scan QR code from screen",
                    icon_name="view-barcode-qr-symbolic",
                    action=lambda name=account_name: self._scan_qr_and_add_account(
                        name
                    ),
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={"type": "qr_scan"},
                ),
            ]

    def _scan_qr_and_add_account(self, account_name: str):
        """Scan QR code and add OTP account."""
        print(f"QR scan action called for account: '{account_name}'")
        print("Starting QR scan process asynchronously...")

        # Run QR scanning asynchronously so launcher closes immediately
        import threading

        thread = threading.Thread(target=self._scan_qr_async, args=(account_name,))
        thread.daemon = True
        thread.start()

    def _scan_qr_async(self, account_name: str):
        """Async QR scanning process."""
        result = scan_qr_and_add_account(account_name, str(self.secrets_file))

        if result["success"]:
            print(result["message"])
            # Reload secrets from file
            self._load_secrets()
            # Trigger refresh to show the new account
            self._trigger_refresh()
        else:
            print(f"QR scan failed: {result['error']}")

    def _handle_remove_command(self, account_name: str) -> List[Result]:
        """Handle removal of OTP account."""
        if not account_name:
            # Show all available accounts for removal
            results = []

            if not self.secrets:
                results.append(
                    Result(
                        title="No OTP accounts to remove",
                        subtitle="Use 'add <account> <secret>' to add accounts first",
                        icon_name="info",
                        action=lambda: None,
                        relevance=1.0,
                        plugin_name=self.display_name,
                        data={"type": "empty", "keep_launcher_open": True},
                    )
                )
            else:
                results.append(
                    Result(
                        title="Select account to remove:",
                        subtitle="Type: remove <account_name> to remove an account",
                        icon_name="user-trash-symbolic",
                        action=lambda: None,
                        relevance=1.0,
                        plugin_name=self.display_name,
                        data={"type": "help", "keep_launcher_open": True},
                    )
                )

                # Get time display for consistency with main OTP view
                time_display = self._get_time_remaining_with_blink()

                # Show all accounts with their current OTP codes and remove actions
                for acc_name, account_data in self.secrets.items():
                    secret = account_data.get("secret", "")
                    issuer = account_data.get("issuer", "")
                    display_name = f"{issuer} - {acc_name}" if issuer else acc_name

                    # Generate current TOTP code
                    totp_code = self._generate_totp(secret)

                    if totp_code:
                        results.append(
                            Result(
                                title=f"{totp_code}",
                                subtitle_markup=f"Press Enter to remove • {
                                    time_display
                                } remaining",
                                icon_name="user-trash-symbolic",
                                action=lambda acc=acc_name: self._remove_account_and_refresh(
                                    acc
                                ),
                                relevance=0.9,
                                plugin_name=self.display_name,
                                data={
                                    "type": "remove_instruction",
                                    "account": acc_name,
                                    "code": totp_code,
                                    "keep_launcher_open": True,
                                },
                            )
                        )
                    else:
                        results.append(
                            Result(
                                title=f"Error: {acc_name}",
                                subtitle="Press Enter to remove (Invalid secret)",
                                icon_name="user-trash-symbolic",
                                action=lambda acc=acc_name: self._remove_account_and_refresh(
                                    acc
                                ),
                                relevance=0.8,
                                plugin_name=self.display_name,
                                data={
                                    "type": "remove_instruction",
                                    "account": acc_name,
                                    "keep_launcher_open": True,
                                },
                            )
                        )

            return results

        # Check if account exists
        if account_name not in self.secrets:
            return [
                Result(
                    title=f"Account '{account_name}' not found",
                    subtitle="Use 'remove' to see all available accounts",
                    icon_name="dialog-cancel-symbolic",
                    action=lambda: None,
                    relevance=0.5,
                    plugin_name=self.display_name,
                    data={"type": "error", "keep_launcher_open": True},
                )
            ]

        # Get account info for confirmation
        account_data = self.secrets[account_name]
        issuer = account_data.get("issuer", "")
        display_name = f"{issuer} - {account_name}" if issuer else account_name

        # Show confirmation for removal
        return [
            Result(
                title=f"Remove '{display_name}'?",
                subtitle="Press Enter to confirm removal",
                icon_name="user-trash-symbolic",
                action=lambda acc=account_name: self._remove_account_and_refresh(acc),
                relevance=1.0,
                plugin_name=self.display_name,
                data={
                    "type": "remove_confirm",
                    "account": account_name,
                    "keep_launcher_open": True,
                },
            )
        ]

    def _handle_base32_secret(self, account_name: str, secret: str) -> List[Result]:
        """Handle raw Base32 secret."""
        result = validate_base32_secret(secret)

        if not result["success"]:
            return [
                Result(
                    title="Invalid Base32 secret",
                    subtitle=result["error"],
                    icon_name="dialog-cancel-symbolic",
                    action=lambda: None,
                    relevance=0.5,
                    plugin_name=self.display_name,
                    data={"type": "error", "keep_launcher_open": True},
                )
            ]

        self.secrets[account_name] = {
            "secret": result["secret"],
            "issuer": "",
            "algorithm": "SHA1",
            "digits": 6,
            "period": 30,
        }
        self._save_secrets()

        return [
            Result(
                title=f"✓ Added '{account_name}'",
                subtitle=f"OTP account added successfully (secret: {
                    result['secret'][:4]
                }...)",
                icon_name="emblem-ok-symbolic",
                action=lambda: self._trigger_refresh(),
                relevance=1.0,
                plugin_name=self.display_name,
                data={"type": "success", "keep_launcher_open": True},
            )
        ]

    def _handle_otpauth_uri(self, account_name: str, uri: str) -> List[Result]:
        """Handle otpauth:// URI."""
        result = parse_otpauth_uri(uri, account_name)

        if not result["success"]:
            return [
                Result(
                    title="Error parsing otpauth URI",
                    subtitle=result["error"],
                    icon_name="dialog-cancel-symbolic",
                    action=lambda: None,
                    relevance=0.5,
                    plugin_name=self.display_name,
                    data={"type": "error", "keep_launcher_open": True},
                )
            ]

        self.secrets[result["account_name"]] = {
            "secret": result["secret"],
            "issuer": result["issuer"],
            "algorithm": result["algorithm"],
            "digits": result["digits"],
            "period": result["period"],
        }
        self._save_secrets()

        display_name = (
            f"{result['issuer']} - {result['account_name']}"
            if result["issuer"]
            else result["account_name"]
        )
        return [
            Result(
                title=f"✓ Added '{display_name}'",
                subtitle="OTP account added from URI",
                icon_name="emblem-ok-symbolic",
                action=lambda: self._trigger_refresh(),
                relevance=1.0,
                plugin_name=self.display_name,
                data={"type": "success", "keep_launcher_open": True},
            )
        ]
