class DesktopWidgetRegistry:
    _widgets = {}
    _sizes = {}
    _default_positions = {}
    _user_keys: set[str] = set()

    @classmethod
    def register(
        cls,
        key: str,
        widget_cls,
        size: tuple[int, int],
        default_position: tuple[float, float] | None = None,
    ):
        cls._widgets[key] = widget_cls
        cls._sizes[key] = size
        if default_position is not None:
            cls._default_positions[key] = default_position

    @classmethod
    def register_user(cls, key: str) -> None:
        cls._user_keys.add(key)

    @classmethod
    def unregister_user_keys(cls, keys: set[str]) -> None:
        for key in keys:
            cls._widgets.pop(key, None)
            cls._sizes.pop(key, None)
            cls._default_positions.pop(key, None)
            cls._user_keys.discard(key)

    @classmethod
    def get_widget_class(cls, key: str):
        return cls._widgets.get(key)

    @classmethod
    def get_widget_size(cls, key: str) -> tuple[int, int]:
        return cls._sizes.get(key, (174, 174))

    @classmethod
    def get_default_position(cls, key: str) -> tuple[float, float] | None:
        return cls._default_positions.get(key)
