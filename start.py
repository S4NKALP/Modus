import os
import sys

# Ensure the 'src' directory is in the python path
# This allows 'import main' and other src-relative imports to work from the root
src_path = os.path.join(os.path.dirname(__file__), "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# App-capture library paths (built via meson in src/window/switcher/app-capture/builddir)
_app_capture_builddir = os.path.join(
    src_path, "window", "switcher", "app-capture", "builddir"
)
if os.path.isdir(_app_capture_builddir):
    for env_var in ("GI_TYPELIB_PATH", "LD_LIBRARY_PATH"):
        current = os.environ.get(env_var, "")
        if _app_capture_builddir not in current.split(os.pathsep):
            os.environ[env_var] = (
                f"{_app_capture_builddir}{os.pathsep}{current}"
                if current
                else _app_capture_builddir
            )


# Apply monkey patch for hyprland lua dispatcher
def run_app():
    from main import main as app_main

    app_main()


def run_lock():
    from window.lock import main as lock_main

    lock_main()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "lock":
        run_lock()
    else:
        run_app()
