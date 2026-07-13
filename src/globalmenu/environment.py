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

# Marker lines previously written around the global LD_PRELOAD export in shell
# rc files. Kept so we can strip the stale block from already-configured systems.
_SHIM_BEGIN = "# >>> modus global-menu shim >>>"
_SHIM_END = "# <<< modus global-menu shim <<<"


def _remove_global_ld_preload():
    """Strip the legacy global LD_PRELOAD export from previously configured systems.

    The shim is now injected per-launch into GTK3 apps only (see
    globalmenu.launch). Any globally exported LD_PRELOAD must be removed so it
    no longer breaks GTK4 processes.
    """
    home = Path.home()
    shell = os.environ.get("SHELL", "")
    rc_files = [
        home / ".zshrc",
        home / ".bashrc",
        home / ".profile",
        home / ".config" / "fish" / "config.fish",
    ]
    rc_path = {
        "zsh": home / ".zshrc",
        "bash": home / ".bashrc",
        "fish": home / ".config" / "fish" / "config.fish",
    }.get(Path(shell).name)
    if rc_path:
        rc_files.append(rc_path)
    rc_files = list(dict.fromkeys(rc_files))  # de-dupe, keep order

    for rc in rc_files:
        try:
            if not rc.is_file():
                continue
            lines = rc.read_text().splitlines(keepends=True)
            if not any(_SHIM_BEGIN in ln for ln in lines):
                continue
            out = []
            drop = False
            for ln in lines:
                if _SHIM_BEGIN in ln:
                    drop = True
                    continue
                if _SHIM_END in ln:
                    drop = False
                    continue
                if drop:
                    continue
                out.append(ln)
            rc.write_text("".join(out))
            logger.info(f"[GlobalMenu] Removed stale LD_PRELOAD block from {rc}")
        except OSError:
            pass

    # Strip the LD_PRELOAD line from environment.d/appmenu.conf.
    env_path = home / ".config" / "environment.d" / "appmenu.conf"
    try:
        if env_path.is_file():
            kept = [
                ln
                for ln in env_path.read_text().splitlines(keepends=True)
                if not ln.strip().startswith("LD_PRELOAD=")
            ]
            env_path.write_text("".join(kept))
    except OSError:
        pass

    # Clear it from the activation environment for future launches.
    exec_shell_command("dbus-update-activation-environment --systemd LD_PRELOAD=")


def get_compiled_shim() -> Path | None:
    """Compile the GTK3 menu-button shim if needed. Returns path to .so or None."""
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


def setup_global_menu_environment():
    """Write env config files so GTK apps register with AppMenu at next login.

    Does NOT set env via hyprctl keyword env — that would cause Fabric's own
    GTK windows to load appmenu-gtk-module and trigger Gdk-CRITICAL assertions.
    Uses session-level config files that take effect at login.
    """
    try:
        shim_path = get_compiled_shim()

        # Remove any legacy global LD_PRELOAD export from older installs.
        _remove_global_ld_preload()

        # NOTE: The menu-button shim is compiled against GTK3 and must NOT be
        # exported globally. Injecting it into a GTK4 process aborts the app
        # ("GTK 2/3 symbols detected"). It is injected per-launch into GTK3
        # apps only — see globalmenu.launch.
        if shim_path:
            logger.debug(f"[GlobalMenu] GTK3 shim ready at {shim_path}")

        exec_shell_command(
            "dbus-update-activation-environment --systemd "
            "GTK_MODULES=appmenu-gtk-module UBUNTU_MENUPROXY=1"
        )

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

        logger.info("[GlobalMenu] GTK environment injected")
    except Exception as e:
        logger.warning(f"[GlobalMenu] Environment setup failed: {e}")
