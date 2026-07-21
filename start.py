import os
import sys


def setup_environment():
    """Ensure the src directory is in sys.path and configure C library paths."""
    src_path = os.path.join(os.path.dirname(__file__), "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    # App-capture library paths (built via meson in src/window/switcher/app-capture/builddir)
    app_capture_builddir = os.path.join(
        src_path, "window", "switcher", "app-capture", "builddir"
    )

    if os.path.isdir(app_capture_builddir):
        for env_var in ("GI_TYPELIB_PATH", "LD_LIBRARY_PATH"):
            current = os.environ.get(env_var, "")
            if app_capture_builddir not in current.split(os.pathsep):
                os.environ[env_var] = (
                    f"{app_capture_builddir}{os.pathsep}{current}"
                    if current
                    else app_capture_builddir
                )


def run_app():
    """Start the main Modus application."""
    from main import main as app_main

    app_main()


def run_lock():
    """Start the lock screen."""
    from window.lock import main as lock_main

    lock_main()


def run_spotlight(argv):
    """Start the spotlight search interface."""
    from window.spotlight.app import main as spotlight_main

    external = "--external" in argv
    positional = [arg for arg in argv if arg != "--external"]

    command = positional[0] if positional else ""
    text = " ".join(positional[1:]) if len(positional) > 1 else ""

    spotlight_main(command=command, text=text, external=external)


def main():
    setup_environment()

    # Route the command based on arguments
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "lock":
            run_lock()
            return
        elif command == "spotlight":
            run_spotlight(sys.argv[2:])
            return

    # Default to running the main app
    run_app()


if __name__ == "__main__":
    main()
