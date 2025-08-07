import json
import os
import threading
from typing import Dict, List, Optional

from loguru import logger

# Threading helper functions


def thread(target, *args, **kwargs) -> threading.Thread:
    """
    Simply run the given function in a thread.
    The provided args and kwargs will be passed to the function.
    """
    th = threading.Thread(target=target, args=args, kwargs=kwargs, daemon=True)
    th.start()
    return th


def run_in_thread(func):
    """
    Decorator to run the decorated function in a thread.
    """

    def wrapper(*args, **kwargs):
        return thread(func, *args, **kwargs)

    return wrapper


@run_in_thread
def write_json_file(data: Dict, path: str):
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Failed to write json: {e}")


def read_json_file(file_path: str) -> Optional[List]:
    if not os.path.exists(file_path):
        logger.error(f"JSON file {file_path} does not exist.")
        return None

    with open(file_path, "r") as file:
        try:
            return json.load(file)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to read JSON file {file_path}: {e}")
            return None
