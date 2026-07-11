"""Global menu environment setup — GTK_MODULES, UBUNTU_MENUPROXY, settings.ini, Flatpak."""

import os
import subprocess
from pathlib import Path

from fabric.utils import exec_shell_command, logger

SHIM_SRC = Path(__file__).resolve().parent / "libmenu_button_shim.c"
SHIM_SO = Path(__file__).resolve().parent / "libmenu_button_shim.so"

ENV_VARS = {
    "GTK_MODULES": "appmenu-gtk-module",
    "UBUNTU_MENUPROXY": "1",
}

_SHIM_BEGIN = "# >>> modus global-menu shim >>>"
_SHIM_END = "# <<< modus global-menu shim <<<"


def _compile_shim() -> Path | None:
    """Compile the menu-button shim if needed. Returns path to .so or None."""
    try:
        if SHIM_SO.exists() and SHIM_SO.stat().st_mtime >= SHIM_SRC.stat().st_mtime:
            return SHIM_SO

        if not SHIM_SRC.exists():
            logger.debug("[GlobalMenu] Shim source not found, skipping")
            return None

        gtk_cflags = subprocess.check_output(
            ["pkg-config", "--cflags", "--libs", "gtk+-3.0"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        cmd = f"gcc -shared -fPIC -O2 -o {SHIM_SO} {SHIM_SRC} {gtk_cflags} -ldl"
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            logger.warning(f"[GlobalMenu] Shim compilation failed:\n{result.stderr}")
            return None

        logger.info(f"[GlobalMenu] Compiled menu shim -> {SHIM_SO}")
        return SHIM_SO
    except Exception as e:
        logger.warning(f"[GlobalMenu] Shim compilation error: {e}")
        return None


def _write_shell_rc(shim_path: Path | None):
    """Append LD_PRELOAD export to the user's shell rc file."""
    if not shim_path:
        return

    shell = os.environ.get("SHELL", "")
    home = Path.home()

    rc_map = {
        "zsh": home / ".zshrc",
        "bash": home / ".bashrc",
        "fish": home / ".config" / "fish" / "config.fish",
    }

    rc_path = rc_map.get(Path(shell).name)
    if rc_path is None:
        rc_path = home / ".profile"

    try:
        if not rc_path.exists():
            return
        existing = rc_path.read_text()
        if _SHIM_BEGIN in existing:
            return

        is_fish = rc_path.name == "config.fish"
        with open(rc_path, "a") as f:
            f.write(f"\n{_SHIM_BEGIN}\n")
            if is_fish:
                f.write(f"set -gx LD_PRELOAD {shim_path}\n")
            else:
                f.write(f"export LD_PRELOAD={shim_path}\n")
            f.write(f"{_SHIM_END}\n")
    except OSError:
        pass


def setup_global_menu_environment():
    """Write env config files so GTK apps register with AppMenu at next login.

    Does NOT set env via hyprctl keyword env — that would cause Fabric's own
    GTK windows to load appmenu-gtk-module and trigger Gdk-CRITICAL assertions.
    Uses session-level config files that take effect at login.
    """
    try:
        shim_path = _compile_shim()

        exec_shell_command(
            "dbus-update-activation-environment --systemd "
            "GTK_MODULES=appmenu-gtk-module UBUNTU_MENUPROXY=1"
        )
        if shim_path:
            exec_shell_command(
                f"dbus-update-activation-environment --systemd LD_PRELOAD={shim_path}"
            )
            exec_shell_command("systemctl --user import-environment LD_PRELOAD")

        exec_shell_command(
            "flatpak override --user --talk-name=com.canonical.AppMenu.Registrar"
        )

        env_dir = Path.home() / ".config" / "environment.d"
        try:
            env_dir.mkdir(parents=True, exist_ok=True)
            env_path = env_dir / "appmenu.conf"
            with open(env_path, "w") as f:
                for k, v in ENV_VARS.items():
                    f.write(f"{k}={v}\n")
                if shim_path:
                    f.write(f"LD_PRELOAD={shim_path}\n")
        except OSError:
            pass

        settings_path = Path.home() / ".config" / "gtk-3.0" / "settings.ini"
        try:
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            content = ""
            if settings_path.exists():
                content = settings_path.read_text()
            if "gtk-shell-shows-menubar" not in content:
                with open(settings_path, "a") as f:
                    if content and not content.endswith("\n"):
                        f.write("\n")
                    f.write("gtk-shell-shows-menubar=1\n")
        except OSError:
            pass

        pam_path = Path.home() / ".pam_environment"
        try:
            existing = ""
            if pam_path.exists():
                existing = pam_path.read_text()
            lines = existing.splitlines(True)
            for k, v in ENV_VARS.items():
                line = f"{k} DEFAULT={v}\n"
                if not any(ln.startswith(f"{k} ") for ln in lines):
                    with open(pam_path, "a") as f:
                        f.write(line)
        except OSError:
            pass

        _write_shell_rc(shim_path)

        logger.info("[GlobalMenu] GTK environment injected")
    except Exception as e:
        logger.warning(f"[GlobalMenu] Environment setup failed: {e}")
