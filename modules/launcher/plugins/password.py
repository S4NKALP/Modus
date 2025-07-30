import base64
import json
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from fabric.utils import get_relative_path

import utils.icons as icons
from modules.launcher.plugin_base import PluginBase
from modules.launcher.result import Result


class PasswordManager:
    """Simple password manager with basic encryption and caching."""

    def __init__(self, storage_file: Path):
        self.storage_file = storage_file
        self.passwords: Dict[str, Dict] = {}
        self._cache_lock = threading.Lock()
        self._last_loaded = 0
        self._cache_ttl = 30  # Cache for 30 seconds
        self._load_passwords()

    def _simple_encrypt(self, text: str, key: str = "modus_pass") -> str:
        """Simple encryption using XOR with base64 encoding."""
        key_bytes = key.encode("utf-8")
        text_bytes = text.encode("utf-8")

        # XOR encryption
        encrypted = bytearray()
        for i, byte in enumerate(text_bytes):
            encrypted.append(byte ^ key_bytes[i % len(key_bytes)])

        # Base64 encode
        return base64.b64encode(encrypted).decode("utf-8")

    def _simple_decrypt(self, encrypted_text: str, key: str = "modus_pass") -> str:
        """Simple decryption using XOR with base64 decoding."""
        try:
            key_bytes = key.encode("utf-8")

            # Base64 decode
            encrypted_bytes = base64.b64decode(encrypted_text.encode("utf-8"))

            # XOR decryption
            decrypted = bytearray()
            for i, byte in enumerate(encrypted_bytes):
                decrypted.append(byte ^ key_bytes[i % len(key_bytes)])

            return decrypted.decode("utf-8")
        except Exception:
            return encrypted_text  # Return as-is if decryption fails

    def _load_passwords(self):
        """Load passwords from JSON file with caching."""
        with self._cache_lock:
            current_time = time.time()

            # Check if cache is still valid
            if (current_time - self._last_loaded) < self._cache_ttl and self.passwords:
                return

            try:
                if self.storage_file.exists():
                    with open(self.storage_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self.passwords = data.get("passwords", {})
                else:
                    self.passwords = {}

                self._last_loaded = current_time
            except Exception as e:
                print(f"Error loading passwords: {e}")
                self.passwords = {}

    def _save_passwords(self):
        """Save passwords to JSON file."""
        with self._cache_lock:
            try:
                self.storage_file.parent.mkdir(parents=True, exist_ok=True)
                data = {
                    "passwords": self.passwords,
                    "last_modified": datetime.now().isoformat(),
                }
                with open(self.storage_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)

                # Update cache timestamp
                self._last_loaded = time.time()
            except Exception as e:
                print(f"Error saving passwords: {e}")

    def add_password(self, name: str, password: str, description: str = "") -> bool:
        """Add a new password entry."""
        try:
            encrypted_password = self._simple_encrypt(password)
            self.passwords[name] = {
                "password": encrypted_password,
                "description": description,
                "created": datetime.now().isoformat(),
                "last_accessed": None,
            }
            self._save_passwords()
            return True
        except Exception as e:
            print(f"Error adding password: {e}")
            return False

    def get_password(self, name: str, update_access_time: bool = True) -> Optional[str]:
        """Get decrypted password by name."""
        # Ensure we have fresh data
        self._load_passwords()

        if name in self.passwords:
            try:
                encrypted = self.passwords[name]["password"]
                decrypted = self._simple_decrypt(encrypted)

                # Update last accessed time only if requested (to avoid frequent saves)
                if update_access_time:
                    self.passwords[name]["last_accessed"] = datetime.now().isoformat()
                    # Don't save immediately - batch saves for better performance

                return decrypted
            except Exception as e:
                print(f"Error decrypting password: {e}")
                return None
        return None

    def remove_password(self, name: str) -> bool:
        """Remove a password entry."""
        if name in self.passwords:
            del self.passwords[name]
            self._save_passwords()
            return True
        return False

    def list_passwords(self) -> List[str]:
        """Get list of all password names."""
        # Ensure we have fresh data
        self._load_passwords()
        return list(self.passwords.keys())

    def get_password_info(self, name: str) -> Optional[Dict]:
        """Get password metadata without decrypting."""
        if name in self.passwords:
            info = self.passwords[name].copy()
            info.pop("password", None)  # Remove encrypted password
            return info
        return None


class PasswordPlugin(PluginBase):
    """
    Password manager plugin for the launcher.
    Stores passwords securely and allows easy access.
    """

    def __init__(self):
        super().__init__()
        self.display_name = "Password Manager"
        self.description = "Secure password storage and management"

        # Initialize password manager
        self.password_file = Path(
            get_relative_path("../../../config/assets/passwords.json")
        )
        self.password_manager = PasswordManager(self.password_file)

        # State for password visibility
        self.revealed_passwords: Dict[str, str] = {}

        # Cache for results to avoid repeated queries
        self._results_cache: Dict[str, List[Result]] = {}
        self._cache_timestamps: Dict[str, float] = {}
        self._cache_ttl = 5  # Cache results for 5 seconds

        # Track launcher state for auto-hiding passwords
        self._launcher_instance = None

    def initialize(self):
        """Initialize the password plugin."""
        self.set_triggers(["pass"])
        self._setup_launcher_hooks()

    def cleanup(self):
        """Cleanup the password plugin."""
        self.revealed_passwords.clear()
        self._results_cache.clear()
        self._cache_timestamps.clear()
        self._cleanup_launcher_hooks()

    def query(self, query_string: str) -> List[Result]:
        """Process password manager queries with caching."""
        query_key = query_string.strip()
        current_time = time.time()

        # Check cache first (except for add/remove commands which should always execute)
        if (
            not query_key.startswith(("add ", "remove ", "delete "))
            and query_key in self._results_cache
            and (current_time - self._cache_timestamps.get(query_key, 0))
            < self._cache_ttl
        ):
            return self._results_cache[query_key]

        results = []
        query = query_key.lower()

        # Handle different commands
        if not query:
            # Show all passwords
            results.extend(self._list_all_passwords())
        elif query.startswith("add "):
            # Add new password (don't cache)
            results.extend(self._handle_add_command(query_string))
        elif query.startswith("remove ") or query.startswith("delete "):
            # Remove password (don't cache)
            results.extend(self._handle_remove_command(query_string))
        else:
            # Search for specific password
            results.extend(self._search_passwords(query))

        # Cache results (except for add/remove commands)
        if not query.startswith(("add ", "remove ", "delete ")):
            self._results_cache[query_key] = results
            self._cache_timestamps[query_key] = current_time

        return results

    def _list_all_passwords(self) -> List[Result]:
        """List all stored passwords."""
        results = []
        password_names = self.password_manager.list_passwords()

        if not password_names:
            results.append(
                Result(
                    title="No passwords stored",
                    subtitle="Use 'pass add <name> <password>' to add your first password",
                    icon_markup=icons.key,
                    action=lambda: None,
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={"type": "empty", "keep_launcher_open": True},
                )
            )
            results.append(
                Result(
                    title="Available commands:",
                    subtitle="add <name> <password> | remove <name> | <name> (to search)",
                    icon_markup=icons.info,
                    action=lambda: None,
                    relevance=0.9,
                    plugin_name=self.display_name,
                    data={"type": "help", "keep_launcher_open": True},
                )
            )
            return results

        # Sort passwords alphabetically
        password_names.sort()

        for name in password_names:
            info = self.password_manager.get_password_info(name)
            description = info.get("description", "") if info else ""

            # Check if password is revealed
            if name in self.revealed_passwords:
                title = f"{name}: {self.revealed_passwords[name]}"
                subtitle = "Password revealed - Enter: copy | Shift+Enter: hide"
            else:
                title = f"{name}: {'*' * 8}"
                subtitle = "Enter: copy | Shift+Enter: reveal password"

            if description:
                subtitle += f" | {description}"

            results.append(
                Result(
                    title=title,
                    subtitle=subtitle,
                    icon_markup=icons.key,
                    action=lambda n=name: self._copy_password_to_clipboard(n),
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={
                        "type": "password",
                        "name": name,
                        "keep_launcher_open": False,
                        "alt_action": lambda n=name: self._toggle_password_visibility(
                            n
                        ),
                    },
                )
            )

        return results

    def _handle_add_command(self, query_string: str) -> List[Result]:
        """Handle add password command."""
        results = []
        parts = query_string.strip().split(" ", 3)

        if len(parts) < 3:
            results.append(
                Result(
                    title="Add Password - Invalid format",
                    subtitle="Usage: add <name> <password> [description]",
                    icon_markup=icons.cancel,
                    action=lambda: None,
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={"type": "error", "keep_launcher_open": True},
                )
            )
            return results

        name = parts[1]
        password = parts[2]
        description = parts[3] if len(parts) > 3 else ""

        # Check if password already exists
        if name in self.password_manager.list_passwords():
            results.append(
                Result(
                    title=f"Update password for '{name}'?",
                    subtitle="Password already exists. Click to update it.",
                    icon_markup=icons.key,
                    action=lambda: self._add_password_action(
                        name, password, description, update=True
                    ),
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={"type": "update", "name": name, "keep_launcher_open": False},
                )
            )
        else:
            results.append(
                Result(
                    title=f"Add password for '{name}'",
                    subtitle="Click to save password"
                    + (f" | {description}" if description else ""),
                    icon_markup=icons.plus,
                    action=lambda: self._add_password_action(
                        name, password, description
                    ),
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={"type": "add", "name": name, "keep_launcher_open": False},
                )
            )

        return results

    def _handle_remove_command(self, query_string: str) -> List[Result]:
        """Handle remove password command."""
        results = []
        parts = query_string.strip().split(" ", 1)

        if len(parts) < 2:
            results.append(
                Result(
                    title="Remove Password - Invalid format",
                    subtitle="Usage: remove <name>",
                    icon_markup=icons.cancel,
                    action=lambda: None,
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={"type": "error", "keep_launcher_open": True},
                )
            )
            return results

        name = parts[1]

        if name not in self.password_manager.list_passwords():
            results.append(
                Result(
                    title=f"Password '{name}' not found",
                    subtitle="Check the name and try again",
                    icon_markup=icons.cancel,
                    action=lambda: None,
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={"type": "error", "keep_launcher_open": True},
                )
            )
        else:
            results.append(
                Result(
                    title=f"Remove password '{name}'?",
                    subtitle="Click to confirm deletion (this cannot be undone)",
                    icon_markup=icons.trash,
                    action=lambda: self._remove_password_action(name),
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={"type": "remove", "name": name, "keep_launcher_open": False},
                )
            )

        return results

    def _search_passwords(self, query: str) -> List[Result]:
        """Search for passwords by name."""
        results = []
        password_names = self.password_manager.list_passwords()

        # Filter passwords that match the query
        matching_passwords = [
            name for name in password_names if query.lower() in name.lower()
        ]

        if not matching_passwords:
            results.append(
                Result(
                    title=f"No passwords found matching '{query}'",
                    subtitle="Try a different search term or use 'pass' to see all passwords",
                    icon_markup=icons.magnifier,
                    action=lambda: None,
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={"type": "no_results", "keep_launcher_open": True},
                )
            )
            return results

        # Sort by relevance (exact match first, then starts with, then contains)
        def get_relevance(name: str) -> float:
            name_lower = name.lower()
            query_lower = query.lower()

            if name_lower == query_lower:
                return 1.0
            elif name_lower.startswith(query_lower):
                return 0.9
            else:
                return 0.7

        matching_passwords.sort(key=get_relevance, reverse=True)

        for name in matching_passwords:
            info = self.password_manager.get_password_info(name)
            description = info.get("description", "") if info else ""

            # Check if password is revealed
            if name in self.revealed_passwords:
                title = f"{name}: {self.revealed_passwords[name]}"
                subtitle = "Password revealed - Enter: copy | Shift+Enter: hide"
            else:
                title = f"{name}: {'*' * 8}"
                subtitle = "Enter: copy | Shift+Enter: reveal password"

            if description:
                subtitle += f" | {description}"

            results.append(
                Result(
                    title=title,
                    subtitle=subtitle,
                    icon_markup=icons.key,
                    action=lambda n=name: self._copy_password_to_clipboard(n),
                    relevance=get_relevance(name),
                    plugin_name=self.display_name,
                    data={
                        "type": "password",
                        "name": name,
                        "keep_launcher_open": False,
                        "alt_action": lambda n=name: self._toggle_password_visibility(
                            n
                        ),
                    },
                )
            )

        return results

    def _add_password_action(
        self, name: str, password: str, description: str = "", update: bool = False
    ):
        """Action to add/update a password."""
        try:
            success = self.password_manager.add_password(name, password, description)
            if success:
                action_word = "updated" if update else "added"
                # Clear cache to force refresh
                self._results_cache.clear()

                # Send notification if available (non-blocking)
                try:
                    subprocess.Popen(
                        [
                            "notify-send",
                            "Password Manager",
                            f"Password '{name}' {action_word} successfully",
                        ]
                    )
                except:
                    pass
            else:
                print(f"Failed to add password '{name}'")
        except Exception as e:
            print(f"Error adding password: {e}")

    def _remove_password_action(self, name: str):
        """Action to remove a password."""
        try:
            success = self.password_manager.remove_password(name)
            if success:
                # Remove from revealed passwords if present
                self.revealed_passwords.pop(name, None)

                # Clear cache to force refresh
                self._results_cache.clear()

                # Send notification if available (non-blocking)
                try:
                    subprocess.Popen(
                        [
                            "notify-send",
                            "Password Manager",
                            f"Password '{name}' removed successfully",
                        ]
                    )
                except:
                    pass
            else:
                print(f"Failed to remove password '{name}'")
        except Exception as e:
            print(f"Error removing password: {e}")

    def _copy_password_to_clipboard(self, name: str):
        """Copy password to clipboard and reveal it temporarily."""
        try:
            password = self.password_manager.get_password(
                name, update_access_time=False
            )
            if password:
                # Copy to clipboard (use timeout to avoid hanging)
                try:
                    subprocess.run(
                        ["wl-copy"], input=password.encode(), check=True, timeout=2
                    )
                except subprocess.SubprocessError:
                    # Fall back to X11
                    subprocess.run(
                        ["xclip", "-selection", "clipboard"],
                        input=password.encode(),
                        check=True,
                        timeout=2,
                    )

                # Reveal password temporarily
                self.revealed_passwords[name] = password

                # Send notification if available (non-blocking)
                try:
                    subprocess.Popen(
                        [
                            "notify-send",
                            "Password Manager",
                            f"Password for '{name}' copied to clipboard",
                        ]
                    )
                except:
                    pass

                # Clear cache to force refresh
                self._results_cache.clear()

            else:
                print(f"Failed to retrieve password for '{name}'")
        except Exception as e:
            print(f"Error copying password: {e}")

    def _reveal_password(self, name: str):
        """Reveal password without copying to clipboard."""
        try:
            password = self.password_manager.get_password(
                name, update_access_time=False
            )
            if password:
                self.revealed_passwords[name] = password
                # Clear cache to force refresh with revealed password
                self._results_cache.clear()
            else:
                print(f"Failed to retrieve password for '{name}'")
        except Exception as e:
            print(f"Error revealing password: {e}")

    def _hide_password(self, name: str):
        """Hide revealed password."""
        self.revealed_passwords.pop(name, None)

    def _hide_all_passwords(self):
        """Hide all revealed passwords."""
        if self.revealed_passwords:
            self.revealed_passwords.clear()
            # Clear cache to force refresh with hidden passwords
            self._results_cache.clear()

    def _setup_launcher_hooks(self):
        """Setup hooks to monitor launcher state."""
        try:
            # Try to find the launcher instance
            import gc

            for obj in gc.get_objects():
                if (
                    hasattr(obj, "__class__")
                    and obj.__class__.__name__ == "Launcher"
                    and hasattr(obj, "close_launcher")
                ):
                    self._launcher_instance = obj
                    # Store original close_launcher method
                    self._original_close_launcher = obj.close_launcher
                    # Replace with our wrapper
                    obj.close_launcher = self._wrapped_close_launcher
                    break
        except Exception as e:
            print(f"Warning: Could not setup launcher hooks: {e}")

    def _cleanup_launcher_hooks(self):
        """Cleanup launcher hooks."""
        try:
            if self._launcher_instance and hasattr(self, "_original_close_launcher"):
                # Restore original close_launcher method
                self._launcher_instance.close_launcher = self._original_close_launcher
                self._launcher_instance = None
        except Exception as e:
            print(f"Warning: Could not cleanup launcher hooks: {e}")

    def _wrapped_close_launcher(self):
        """Wrapper for launcher close that hides passwords."""
        # Hide all passwords when launcher closes
        self._hide_all_passwords()
        # Call original close_launcher method
        if hasattr(self, "_original_close_launcher"):
            self._original_close_launcher()

    def _toggle_password_visibility(self, name: str):
        """Toggle password visibility when Shift+Enter is pressed."""
        if name in self.revealed_passwords:
            # Hide password
            self.revealed_passwords.pop(name, None)
            self._results_cache.clear()
        else:
            # Reveal password
            try:
                password = self.password_manager.get_password(
                    name, update_access_time=False
                )
                if password:
                    self.revealed_passwords[name] = password
                    self._results_cache.clear()
                else:
                    print(f"Failed to retrieve password for '{name}'")
            except Exception as e:
                print(f"Error revealing password: {e}")

        # Force refresh of the launcher to show updated state
        self._force_launcher_refresh()

    def _force_launcher_refresh(self):
        """Force the launcher to refresh and show updated results."""
        try:
            if self._launcher_instance and hasattr(
                self._launcher_instance, "_perform_search"
            ):
                # Get current search text
                current_text = ""
                if hasattr(self._launcher_instance, "search_entry"):
                    current_text = self._launcher_instance.search_entry.get_text()

                # Trigger a search to refresh results
                try:
                    from gi.repository import GLib

                    def refresh():
                        self._launcher_instance._perform_search(current_text)
                        return False

                    GLib.timeout_add(50, refresh)
                except ImportError:
                    # Fallback: direct call if GLib not available
                    self._launcher_instance._perform_search(current_text)
        except Exception as e:
            print(f"Could not force launcher refresh: {e}")
