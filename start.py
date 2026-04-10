import os
import sys

# Ensure the 'src' directory is in the python path
# This allows 'import main' and other src-relative imports to work from the root
src_path = os.path.join(os.path.dirname(__file__), "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)


def run_app():
    from main import main as app_main

    app_main()


def run_lock():
    from lock import main as lock_main

    lock_main()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "lock":
        run_lock()
    else:
        run_app()
