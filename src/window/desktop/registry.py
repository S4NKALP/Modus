from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from fabric.utils import logger


@dataclass(slots=True, frozen=True)
class WidgetInfo:
    widget_cls: type[Any]
    size: tuple[int, int]
    default_position: tuple[float, float] | None = None


class DesktopWidgetRegistry:
    DEFAULT_SIZE: tuple[int, int] = (174, 174)

    _registry: dict[str, WidgetInfo] = {}
    _user_keys: set[str] = set()

    @classmethod
    def register(
        cls,
        key: str,
        widget_cls: type[Any],
        size: tuple[int, int],
        default_position: tuple[float, float] | None = None,
    ) -> None:
        if key in cls._registry:
            logger.warning("Replacing widget '%s'", key)
        cls._registry[key] = WidgetInfo(widget_cls, size, default_position)

    @classmethod
    def register_user(cls, key: str) -> None:
        cls._user_keys.add(key)

    @classmethod
    def unregister(cls, key: str) -> None:
        cls._registry.pop(key, None)
        cls._user_keys.discard(key)

    @classmethod
    def unregister_user_keys(cls, keys: set[str]) -> None:
        for key in keys:
            cls.unregister(key)

    @classmethod
    def clear_user_widgets(cls) -> None:
        cls.unregister_user_keys(set(cls._user_keys))

    @classmethod
    def get_widget_class(cls, key: str) -> type[Any] | None:
        info = cls._registry.get(key)
        return info.widget_cls if info else None

    @classmethod
    def get_widget_size(cls, key: str) -> tuple[int, int]:
        info = cls._registry.get(key)
        return info.size if info else cls.DEFAULT_SIZE

    @classmethod
    def get_default_position(cls, key: str) -> tuple[float, float] | None:
        info = cls._registry.get(key)
        return info.default_position if info else None

    @classmethod
    def is_registered(cls, key: str) -> bool:
        return key in cls._registry

    @classmethod
    def keys(cls) -> tuple[str, ...]:
        return tuple(cls._registry)

    @classmethod
    def widgets(cls) -> MappingProxyType[str, WidgetInfo]:
        return MappingProxyType(cls._registry)
