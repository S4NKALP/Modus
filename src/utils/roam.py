_services_mod = None


def _mod():
    global _services_mod
    if _services_mod is None:
        import services.modus as _services_mod
    return _services_mod


def __getattr__(name):
    if name in (
        "modus_service",
        "notification_service",
        "audio_service",
        "screen_capture_service",
        "screenshot_service",
        "screen_recorder_service",
    ):
        return getattr(_mod(), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
