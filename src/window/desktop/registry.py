class DesktopWidgetRegistry:
    _widgets = {}
    _sizes = {}

    @classmethod
    def register(cls, key: str, widget_cls, size: tuple[int, int]):
        cls._widgets[key] = widget_cls
        cls._sizes[key] = size

    @classmethod
    def get_widget_class(cls, key: str):
        return cls._widgets.get(key)

    @classmethod
    def get_widget_size(cls, key: str) -> tuple[int, int]:
        return cls._sizes.get(key, (174, 174))
