"""Pure-Python mouse click simulation via /dev/uinput."""

import os
import struct
import time as _time

_UI_DEV_CREATE = 0x5501
_UI_SET_EVBIT = 0x40045564
_UI_SET_KEYBIT = 0x40045565
_UI_SET_RELBIT = 0x40045567

_EV_KEY = 0x01
_EV_REL = 0x02
_REL_X = 0x00
_REL_Y = 0x01
_BTN_LEFT = 0x110
_SYN_REPORT = 0

_ABS_CNT = 64
_INPUT_EVENT_FMT = "<qqHHi"


def uinput_click(x: int, y: int, move_first: bool = True) -> bool:
    """Move cursor to (x, y) and left-click using a virtual uinput mouse.

    Returns True on success.
    """
    try:
        fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)

        import fcntl

        for cap in (_EV_KEY, _EV_REL):
            fcntl.ioctl(fd, _UI_SET_EVBIT, cap)
        fcntl.ioctl(fd, _UI_SET_KEYBIT, _BTN_LEFT)
        for rel in (_REL_X, _REL_Y):
            fcntl.ioctl(fd, _UI_SET_RELBIT, rel)

        name = b"OpenCodeMouse\x00" + b"\x00" * 66
        dev = name
        dev += struct.pack("<HHHHI", 0x03, 0x1234, 0x5678, 1, 0)
        dev += b"\x00" * (_ABS_CNT * 4 * 4)
        os.write(fd, dev)
        fcntl.ioctl(fd, _UI_DEV_CREATE)
        _time.sleep(0.15)

        def _emit(etype: int, code: int, value: int):
            os.write(fd, struct.pack(_INPUT_EVENT_FMT, 0, 0, etype, code, value))

        if move_first:
            _emit(_EV_REL, _REL_X, x)
            _emit(_EV_REL, _REL_Y, y)
            _emit(_SYN_REPORT, 0, 0)
            _time.sleep(0.03)

        _emit(_EV_KEY, _BTN_LEFT, 1)
        _emit(_SYN_REPORT, 0, 0)
        _time.sleep(0.03)
        _emit(_EV_KEY, _BTN_LEFT, 0)
        _emit(_SYN_REPORT, 0, 0)

        os.close(fd)
        return True
    except Exception:
        return False
