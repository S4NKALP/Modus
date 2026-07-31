"""GTK3-aware application launching for the global menu compatibility shim.

The legacy LD_PRELOAD approach exported ``libmenu_button_shim.so`` globally.
That shim links against GTK3, so loading it into a GTK4 process crashes the
app. Instead we detect the toolkit of the target executable and inject the
shim only into GTK3 processes, leaving GTK4 (and other) apps untouched.

Two launch paths are supported:

* :func:`launch_command` — for raw command lines (used by the dock launcher
  and forwarded through ``uwsm app``). The shim is prepended via ``env`` so it
  is set only for the spawned process.
* :func:`launch_desktop_app` — for :class:`fabric.utils.DesktopApp` objects,
  which launch through GIO and inherit the current process environment. We
  temporarily set ``LD_PRELOAD`` around the launch call and restore it
  immediately afterwards.
"""

import os
import re
from pathlib import Path

from fabric.utils import exec_shell_command_async, logger

from window.globalmenu.detection import executable_gtk_class
from window.globalmenu.environment import get_compiled_shim

_PERCENT_RE = re.compile(r"%\w+")


def _gtk3_shim() -> str | None:
    """Return the shim path if it is compiled, else ``None``."""
    shim = get_compiled_shim()
    return str(shim) if shim else None


def shim_env_for_executable(executable: str | None) -> dict[str, str] | None:
    """Return ``{"LD_PRELOAD": <shim>}`` for a GTK3 executable, else ``None``."""
    if executable_gtk_class(executable) != "gtk3":
        return None
    shim = _gtk3_shim()
    if not shim:
        return None
    return {"LD_PRELOAD": shim}


def launch_command(command_line: str) -> None:
    """Launch a command through ``uwsm app``, injecting the GTK3 shim if needed."""
    if not command_line:
        return

    cleaned = _PERCENT_RE.sub("", command_line).strip()
    if not cleaned:
        return

    shim_env = shim_env_for_executable(cleaned)
    if shim_env:
        # Scope the shim to the launched process only.
        cleaned = f"env LD_PRELOAD={shim_env['LD_PRELOAD']} {cleaned}"
        logger.debug(f"[GlobalMenu] Injecting GTK3 shim for: {cleaned}")

    exec_shell_command_async(
        f"hyprctl dispatch 'hl.dsp.exec_cmd([[uwsm app -- {cleaned}]])'"
    )


def _launch_workdir(app) -> str | None:
    """Working directory for the launched app: the desktop file's ``Path=``
    if set, else the user's home directory.

    GIO inherits the calling process's cwd when the desktop file has no
    ``Path=`` entry, so without this terminals and file managers would open in
    Modus's own working directory.
    """
    app_path = getattr(app, "_app", None)
    path = app_path.get_string("Path") if app_path is not None else None
    if path:
        return str(path)
    return str(Path.home())


def launch_desktop_app(app) -> None:
    """Launch a :class:`fabric.utils.DesktopApp`, injecting the GTK3 shim if needed."""
    workdir = _launch_workdir(app)
    cwd = os.getcwd()

    def launch() -> None:
        if workdir:
            os.chdir(workdir)
        try:
            app.launch()
        finally:
            os.chdir(cwd)

    shim_env = shim_env_for_executable(getattr(app, "executable", None))
    if shim_env:
        prev = os.environ.get("LD_PRELOAD")
        os.environ["LD_PRELOAD"] = shim_env["LD_PRELOAD"]
        logger.debug(
            f"[GlobalMenu] Injecting GTK3 shim for desktop app: "
            f"{getattr(app, 'display_name', app)}"
        )
        try:
            launch()
        finally:
            if prev is None:
                os.environ.pop("LD_PRELOAD", None)
            else:
                os.environ["LD_PRELOAD"] = prev
    else:
        launch()
