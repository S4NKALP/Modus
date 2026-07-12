import base64
import getpass
import json
import secrets
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from fabric.utils import logger

import config.data as data


class PasswordManager:
    """Password manager service with encryption capabilities"""

    def __init__(self, master_password: str = None):
        self.data_dir = Path(data.plugins) / "passwords"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.passwords_file = self.data_dir / "passwords.json"
        self.key_file = self.data_dir / "key.key"
        self.salt_file = self.data_dir / "salt.key"

        self.master_password = master_password
        self.fernet = None

        self._initialize_password_file()
        self._setup_encryption()

    def _initialize_password_file(self):
        if not self.passwords_file.exists():
            with open(self.passwords_file, "w") as f:
                json.dump({}, f)

    def _setup_encryption(self):
        if self.master_password is None:
            # Prompt for master password securely
            self.master_password = getpass.getpass("Enter master password: ")
            if not self.master_password:
                raise ValueError("Master password cannot be empty")

        # Generate or load the encryption key
        if self.key_file.exists():
            with open(self.key_file, "rb") as f:
                key = f.read()
        else:
            # Generate new key from master password
            key = self._derive_key_from_password(self.master_password)
            with open(self.key_file, "wb") as f:
                f.write(key)

        self.fernet = Fernet(key)

    def _derive_key_from_password(self, password: str) -> bytes:
        # Generate or load cryptographically secure salt
        if self.salt_file.exists():
            with open(self.salt_file, "rb") as f:
                salt = f.read()
        else:
            # Generate cryptographically secure random salt
            salt = secrets.token_bytes(32)
            with open(self.salt_file, "wb") as f:
                f.write(salt)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,  # High iteration count for security
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key

    def _encrypt_password(self, password: str) -> str:
        if self.fernet is None:
            raise ValueError("Encryption not initialized")
        encrypted = self.fernet.encrypt(password.encode())
        return base64.urlsafe_b64encode(encrypted).decode()

    def _decrypt_password(self, encrypted_password: str) -> str:
        if self.fernet is None:
            raise ValueError("Encryption not initialized")
        encrypted_bytes = base64.urlsafe_b64decode(encrypted_password.encode())
        decrypted = self.fernet.decrypt(encrypted_bytes)
        return decrypted.decode()

    def add_password(
        self,
        name: str,
        username: str,
        password: str,
        website: str = "",
        notes: str = "",
    ) -> dict[str, Any]:
        passwords = self._load_passwords()

        if name in passwords:
            return {
                "success": False,
                "error": f"Password entry '{name}' already exists",
            }

        encrypted_password = self._encrypt_password(password)
        passwords[name] = {
            "username": username,
            "password": encrypted_password,
            "website": website,
            "notes": notes,
            "created_at": self._get_timestamp(),
            "updated_at": self._get_timestamp(),
        }

        self._save_passwords(passwords)
        return {
            "success": True,
            "message": f"Password entry '{name}' added successfully",
        }

    def get_password(self, name: str, decrypt: bool = True) -> dict[str, any]:
        passwords = self._load_passwords()

        if name not in passwords:
            return {"success": False, "error": f"Password entry '{name}' not found"}

        entry = passwords[name].copy()

        if not decrypt:
            return {"success": True, "data": entry}

        try:
            entry["password"] = self._decrypt_password(entry["password"])
        except Exception as e:
            logger.error(f"Error decrypting password: {e}")
            return {
                "success": False,
                "error": f"Failed to decrypt password: {str(e)}",
            }

        return {"success": True, "data": entry}

    def update_password(self, name: str, **kwargs) -> dict[str, any]:
        passwords = self._load_passwords()

        if name not in passwords:
            return {"success": False, "error": f"Password entry '{name}' not found"}

        for field, value in kwargs.items():
            if field == "password":
                # Encrypt the password
                passwords[name][field] = self._encrypt_password(value)
            elif field in ["username", "website", "notes"]:
                passwords[name][field] = value
            else:
                logger.warning(f"Unknown field '{field}' ignored")

        passwords[name]["updated_at"] = self._get_timestamp()
        self._save_passwords(passwords)

        return {
            "success": True,
            "message": f"Password entry '{name}' updated successfully",
        }

    def delete_password(self, name: str) -> dict[str, any]:
        passwords = self._load_passwords()

        if name not in passwords:
            return {"success": False, "error": f"Password entry '{name}' not found"}

        del passwords[name]
        self._save_passwords(passwords)

        return {
            "success": True,
            "message": f"Password entry '{name}' deleted successfully",
        }

    def list_passwords(self, decrypt_passwords: bool = False) -> dict[str, any]:
        passwords = self._load_passwords()

        if not decrypt_passwords:
            return {"success": True, "data": passwords, "count": len(passwords)}

        for name, entry in passwords.items():
            if name == "_master_password":
                continue  # Skip master password as it's stored as plain text
            try:
                entry["password"] = self._decrypt_password(entry["password"])
            except Exception as e:
                logger.error(f"Error decrypting password for {name}: {e}")
                entry["password"] = "[DECRYPTION_ERROR]"

        return {"success": True, "data": passwords, "count": len(passwords)}

    def search_passwords(self, query: str) -> dict[str, any]:
        passwords = self._load_passwords()
        query_lower = query.lower()

        matches = {}
        for name, entry in passwords.items():
            # Search in name, username, website, and notes
            searchable_text = f"{name} {entry.get('username', '')} {entry.get('website', '')} {entry.get('notes', '')}".lower()

            if query_lower in searchable_text:
                matches[name] = entry

        return {"success": True, "data": matches, "count": len(matches), "query": query}

    def _load_passwords(self) -> dict[str, Any]:
        with open(self.passwords_file) as f:
            return json.load(f)

    def _save_passwords(self, passwords: dict[str, Any]):
        with open(self.passwords_file, "w") as f:
            json.dump(passwords, f, indent=2)

    def _get_timestamp(self) -> str:
        from datetime import datetime

        return datetime.now().isoformat()

    def verify_master_password(self, password: str) -> bool:
        try:
            if not self.key_file.exists() or not self.salt_file.exists():
                return False

            # Stored key is the urlsafe base64 encoded key bytes
            with open(self.key_file, "rb") as f:
                stored_key = f.read()

            # Derive key from provided password using existing salt
            derived_key = self._derive_key_from_password(password)

            # Constant-time compare
            if secrets.compare_digest(stored_key, derived_key):
                return True

            # Fallback: try decrypting any stored entry with the derived key
            passwords = self._load_passwords()
            if not passwords:
                return False

            test_fernet = Fernet(derived_key)
            for name, entry in passwords.items():
                if name.startswith("_master_"):
                    continue
                try:
                    test_fernet.decrypt(
                        base64.urlsafe_b64decode(entry.get("password", "").encode())
                    )
                    return True
                except Exception:
                    continue
            return False
        except Exception:
            return False

    def change_master_password(
        self, old_password: str, new_password: str
    ) -> dict[str, Any]:
        # Verify old password by trying to decrypt with it
        old_key = self._derive_key_from_password(old_password)
        old_fernet = Fernet(old_key)

        # Test decryption with old password
        passwords = self._load_passwords()
        if passwords:
            # Try to decrypt the first password to verify old password
            first_entry = next(iter(passwords.values()))
            try:
                old_fernet.decrypt(
                    base64.urlsafe_b64decode(first_entry["password"].encode())
                )
            except Exception:
                return {"success": False, "error": "Invalid old master password"}

        # Generate new key
        new_key = self._derive_key_from_password(new_password)
        new_fernet = Fernet(new_key)

        # Re-encrypt all passwords with new key (skip _master_password as it's not encrypted)
        for name, entry in passwords.items():
            if name == "_master_password":
                continue  # Skip master password as it's stored as plain text
            try:
                # Decrypt with old key
                decrypted_password = old_fernet.decrypt(
                    base64.urlsafe_b64decode(entry["password"].encode())
                )
                # Encrypt with new key
                encrypted_password = new_fernet.encrypt(decrypted_password)
                entry["password"] = base64.urlsafe_b64encode(
                    encrypted_password
                ).decode()
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Failed to re-encrypt password for {name}: {str(e)}",
                }

        self._save_passwords(passwords)
        with open(self.key_file, "wb") as f:
            f.write(new_key)

        self.master_password = new_password
        self.fernet = new_fernet
        return {"success": True, "message": "Master password changed successfully"}

    def export_passwords(
        self, file_path: str, include_passwords: bool = True
    ) -> dict[str, Any]:
        passwords = self._load_passwords()

        if not include_passwords:
            export_data = {
                "exported_at": self._get_timestamp(),
                "include_passwords": include_passwords,
                "passwords": passwords,
            }
            with open(file_path, "w") as f:
                json.dump(export_data, f, indent=2)

            return {
                "success": True,
                "message": f"Passwords exported to {file_path}",
                "count": len(passwords),
            }

        # Decrypt passwords for export (skip _master_password as it's not encrypted)
        for name, entry in passwords.items():
            if name == "_master_password":
                continue  # Skip master password as it's stored as plain text
            try:
                entry["password"] = self._decrypt_password(entry["password"])
            except Exception as e:
                logger.error(f"Error decrypting password for {name}: {e}")
                entry["password"] = "[DECRYPTION_ERROR]"

        export_data = {
            "exported_at": self._get_timestamp(),
            "include_passwords": include_passwords,
            "passwords": passwords,
        }
        with open(file_path, "w") as f:
            json.dump(export_data, f, indent=2)

        return {
            "success": True,
            "message": f"Passwords exported to {file_path}",
            "count": len(passwords),
        }
