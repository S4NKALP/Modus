from __future__ import annotations

from modules.launcher.plugins import (
    ApplicationPlugin,
    BluetoothPlugin,
    BookmarkPlugin,
    CaffeinePlugin,
    CalculatorPlugin,
    ClipboardPlugin,
    ColorPickerPlugin,
    EmojiPlugin,
    GoogleLensPlugin,
    NetworkManagerPlugin,
    OTPPlugin,
    PasswordManagerPlugin,
    PowerMenuPlugin,
    PowerProfilePlugin,
    QueryPlugin,
    ReminderPlugin,
    ScreenCapturePlugin,
    SettingsPlugin,
    SSHPlugin,
    TmuxPlugin,
    TodoPlugin,
    WallpaperPlugin,
    WindowSwitcherPlugin,
)


def build_plugins(handler) -> dict[str, object]:
    """Create all plugins."""

    registry: list[tuple[str, object]] = [
        ("wallpaper", WallpaperPlugin),
        ("application", ApplicationPlugin),
        ("bookmark", BookmarkPlugin),
        ("calculator", CalculatorPlugin),
        ("query", QueryPlugin),
        ("emoji", EmojiPlugin),
        ("clipboard", ClipboardPlugin),
        ("otp", OTPPlugin),
        ("password", PasswordManagerPlugin),
        ("tmux", TmuxPlugin),
        ("windows", WindowSwitcherPlugin),
        ("power", PowerProfilePlugin),
        ("powermenu", PowerMenuPlugin),
        ("todo", TodoPlugin),
        ("screen", ScreenCapturePlugin),
        ("caffeine", CaffeinePlugin),
        ("ssh", SSHPlugin),
        ("color", ColorPickerPlugin),
        ("reminder", ReminderPlugin),
        ("network", NetworkManagerPlugin),
        ("bluetooth", BluetoothPlugin),
        ("lens", GoogleLensPlugin),
        ("settings", SettingsPlugin),
    ]

    plugins: dict[str, object] = {}
    for key, cls in registry:
        plugins[key] = cls(handler)

    return plugins
