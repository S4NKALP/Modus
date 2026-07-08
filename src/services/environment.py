"""Global menu environment setup — GTK_MODULES, UBUNTU_MENUPROXY, settings.ini, Flatpak."""

from fabric.utils import exec_shell_command, logger, os


ENV_VARS = {
    "GTK_MODULES": "appmenu-gtk-module",
    "UBUNTU_MENUPROXY": "1",
}


def setup_global_menu_environment():
    """Write env config files so GTK apps register with AppMenu at next login.

    Does NOT set env via hyprctl keyword env — that would cause Fabric's own
    GTK windows to load appmenu-gtk-module and trigger Gdk-CRITICAL assertions.
    Uses session-level config files that take effect at login.
    """
    try:
        # exec_shell_command("hyprctl keyword env GTK_MODULES,appmenu-gtk-module")
        # exec_shell_command("hyprctl keyword env UBUNTU_MENUPROXY,1")
        exec_shell_command(
            "dbus-update-activation-environment --systemd GTK_MODULES=appmenu-gtk-module UBUNTU_MENUPROXY=1"
        )
        exec_shell_command(
            "flatpak override --user --talk-name=com.canonical.AppMenu.Registrar"
        )

        env_dir = os.path.expanduser("~/.config/environment.d")
        try:
            os.makedirs(env_dir, exist_ok=True)
            env_path = os.path.join(env_dir, "appmenu.conf")
            with open(env_path, "w") as f:
                for k, v in ENV_VARS.items():
                    f.write(f"{k}={v}\n")
        except OSError:
            pass

        settings_path = os.path.expanduser("~/.config/gtk-3.0/settings.ini")
        try:
            if not os.path.exists(os.path.dirname(settings_path)):
                os.makedirs(os.path.dirname(settings_path), exist_ok=True)
            content = ""
            if os.path.exists(settings_path):
                with open(settings_path, "r") as f:
                    content = f.read()
            if "gtk-shell-shows-menubar" not in content:
                with open(settings_path, "a") as f:
                    if content and not content.endswith("\n"):
                        f.write("\n")
                    f.write("gtk-shell-shows-menubar=1\n")
        except OSError:
            pass

        pam_path = os.path.expanduser("~/.pam_environment")
        try:
            existing = ""
            if os.path.exists(pam_path):
                with open(pam_path, "r") as f:
                    existing = f.read()
            lines = existing.splitlines(True)
            for k, v in ENV_VARS.items():
                line = f"{k} DEFAULT={v}\n"
                if not any(ln.startswith(f"{k} ") for ln in lines):
                    with open(pam_path, "a") as f:
                        f.write(line)
        except OSError:
            pass

        logger.info("[GlobalMenu] GTK environment injected")
    except Exception as e:
        logger.warning(f"[GlobalMenu] Environment setup failed: {e}")
