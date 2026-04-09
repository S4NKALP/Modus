import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from services.mpris import MprisPlayer


def test_signal_emission():
    # We need a bus name to initialize MprisPlayer, but we won't actually call DBus methods if we don't trigger them
    # However, MprisPlayer.__init__ calls do_register which tries to connect to DBus
    # I'll mock the GioDBusHelper to avoid DBus connection issues

    import utils.dbus_helper

    original_helper = utils.dbus_helper.GioDBusHelper

    class MockDBusHelper:
        def __init__(self, *args, **kwargs):
            self.proxy = None

        def call_method(self, *args, **kwargs):
            pass

        def set_property(self, *args, **kwargs):
            pass

    utils.dbus_helper.GioDBusHelper = MockDBusHelper

    try:
        player = MprisPlayer("org.mpris.MediaPlayer2.mock")

        # Test values
        small_val = 1000
        large_val = 3000000000  # > 2^31 - 1

        print(f"Testing emission with small value: {small_val}")
        player.emit("seeked", small_val)
        print("Success")

        print(f"Testing emission with large value: {large_val}")
        player.emit("seeked", large_val)
        print("Success")

    except Exception as e:
        print(f"Failed: {e}")
        import traceback

        traceback.print_exc()
    finally:
        utils.dbus_helper.GioDBusHelper = original_helper


if __name__ == "__main__":
    test_signal_emission()
