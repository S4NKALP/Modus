from utils.evdev_lock import EvdevLockService


class CapsLock(EvdevLockService):
    """Service for monitoring CapsLock LED state via evdev."""

    _LED_GLOB = "input*::capslock"
    _LED_INDEX = 1  # LED_CAPSL
    _SERVICE_NAME = "CapsLock"

    _instance = None

    @staticmethod
    def get_initial():
        if CapsLock._instance is None:
            CapsLock._instance = CapsLock()
        return CapsLock._instance
