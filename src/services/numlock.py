from utils.evdev_lock import EvdevLockService


class NumLock(EvdevLockService):
    """Service for monitoring NumLock LED state via evdev."""

    _LED_GLOB = "input*::numlock"
    _LED_INDEX = 0  # LED_NUML
    _SERVICE_NAME = "NumLock"

    _instance = None

    @staticmethod
    def get_initial():
        if NumLock._instance is None:
            NumLock._instance = NumLock()
        return NumLock._instance
