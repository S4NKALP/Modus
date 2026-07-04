import functools
import typing as t

from fabric.utils import GLib


def sync_debounce(
    delay: int, min_n_times: int = 0, immediate: bool = False
) -> t.Callable[..., t.Any]:
    def decorator(func: t.Callable[..., t.Any]) -> t.Callable[..., t.Any]:
        n_times = 0
        timeout_id: int | None = None
        last_args: tuple[t.Any, ...] = ()
        last_kwargs: dict[str, t.Any] = {}

        def call_func() -> bool:
            nonlocal timeout_id, n_times
            if n_times > min_n_times:
                func(*last_args, **last_kwargs)
            n_times = 0
            timeout_id = None
            return False

        def wrapper(*args: t.Any, **kwargs: t.Any) -> None:
            nonlocal timeout_id, last_args, last_kwargs, n_times

            last_args = args
            last_kwargs = kwargs

            if timeout_id is not None:
                GLib.source_remove(timeout_id)

            if not immediate or n_times < min_n_times:
                n_times += 1
                timeout_id = GLib.timeout_add(delay, call_func)
            else:
                n_times = 0
                timeout_id = None
                func(*last_args, **last_kwargs)

        return functools.wraps(func)(wrapper)

    return decorator
