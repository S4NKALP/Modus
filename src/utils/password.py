"""Password verification and keyring caching utilities.

Provides PAM-based password verification with su fallback,
and system keyring integration for caching authenticated passwords.
"""

from fabric.utils import logger

from utils.functions import run_command

KEYRING_SERVICE = "sysauth"


def verify_password(username: str, password: str) -> bool:
    """Verify password using PAM with su fallback.

    Args:
        username: The username to authenticate.
        password: The password to verify.

    Returns:
        True if authentication succeeded, False otherwise.
    """
    if _verify_pam(username, password):
        return True
    return _verify_su(username, password)


def _verify_pam(username: str, password: str) -> bool:
    """Verify password using python-pam."""
    try:
        import pam as pam_module

        p = pam_module.pam()
        return p.authenticate(username, password)
    except ImportError:
        return False
    except Exception as e:
        logger.warning(f"[password] PAM verification failed: {e}")
        return False


def _verify_su(username: str, password: str) -> bool:
    """Verify password using the su command as fallback."""
    result = run_command(
        ["su", "-c", "true", username],
        input=password,
        timeout=5,
    )
    return result.returncode == 0


def cache_password(action_id: str, uid: int, password: str) -> None:
    """Cache a password in the system keyring.

    Args:
        action_id: The action identifier.
        uid: The user ID being authenticated.
    """
    kr = _get_keyring()
    if kr is None:
        return

    try:
        cache_key = f"{action_id}:{uid}"
        kr.set_password(KEYRING_SERVICE, cache_key, password)
        logger.debug(f"[password] Cached password for {action_id} (uid={uid})")
    except Exception as e:
        logger.debug(f"[password] Failed to cache password: {e}")


def get_cached_password(action_id: str, uid: int) -> "str | None":
    """Retrieve a cached password from the system keyring.

    Args:
        action_id: The action identifier.
        uid: The user ID being authenticated.

    Returns:
        The cached password, or None if not found.
    """
    kr = _get_keyring()
    if kr is None:
        return None

    try:
        cache_key = f"{action_id}:{uid}"
        password = kr.get_password(KEYRING_SERVICE, cache_key)
        if password:
            logger.debug(
                f"[password] Retrieved cached password for {action_id} (uid={uid})"
            )
        return password
    except Exception as e:
        logger.debug(f"[password] Failed to retrieve cached password: {e}")
        return None


def get_username_from_uid(uid: int) -> "str":
    """Get the username for a given UID.

    Args:
        uid: The user ID.

    Returns:
        The username, or 'root' if lookup fails.
    """
    try:
        import pwd

        return pwd.getpwuid(uid).pw_name
    except (KeyError, ImportError):
        return "root"


def _get_keyring():
    """Get the keyring backend, using keyrings.alt file-based backend."""
    try:
        import keyring as keyring_module

        try:
            from keyrings.alt.file import PlaintextKeyring

            kb = PlaintextKeyring()
            keyring_module.set_keyring(kb)
        except ImportError:
            pass

        return keyring_module
    except ImportError:
        logger.debug("[password] keyring module not available")
        return None
