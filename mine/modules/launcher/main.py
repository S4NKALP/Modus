from fabric.core import Service, Signal
from fabric.utils import GLib, Gdk, Gtk, get_desktop_applications, remove_handler
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from fabric.widgets.image import Image
from fabric.widgets.wayland import WaylandWindow as Window

from utils.animatedscrollable import AnimatedScrollable
from utils.clippingbox import ClippingBox
from utils.functions import add_style_class_lazy, debounce, get_children_height_limit

from modules.launcher.plugin_registry import build_plugins


class Thread:
    def __init__(self, func, *data, name: str | None = None):
        self.func = func
        self.data = data
        self.stopped = False
        self.gthread = GLib.Thread.new(name, self.wrapper, *data)

    def stop(self):
        self.stopped = True

    def wrapper(self, *data):
        while not self.stopped:
            if not self.func(*data):
                break
        return self.gthread.exit()


class LauncherListsHandler(Service):
    @Signal
    def launched(self) -> None: ...

    @Signal
    def slot_ready(self, button: Button, mode: str) -> None: ...

    @Signal
    def start(self, mode: str) -> None: ...

    @Signal
    def done(self) -> None: ...

    def __init__(self, viewport=None, **kwargs):
        super().__init__(**kwargs)
        self._query_handler: int = 0
        self._query_thread: Thread | None = None
        self.viewport = viewport
        self.header_entry = None

        self.plugins = build_plugins(self)

    def stop(self):
        if self._query_handler:
            remove_handler(self._query_handler)
            self._query_handler = 0
        if self._query_thread:
            self._query_thread.stop()
            self._query_thread = None

        for plugin in self.plugins.values():
            if hasattr(plugin, "stop"):
                plugin.stop()
        return

    def __getattr__(self, name: str):
        raise AttributeError(name)

    def clear_viewport(self):
        if self.viewport:
            for old_slot in self.viewport.children:
                self.viewport.remove(old_slot)
                old_slot.destroy()

    def clear_input(self):
        if self.header_entry:
            self.header_entry._ignore_change = True
            self.header_entry.set_text("")


class Launcher(Box):
    @Signal
    def launched(self): ...

    def __init__(self, **kwargs):
        super().__init__(name="launcher", spacing=4, orientation="v", **kwargs)

        self._arranger_handler: int = 0
        self._all_apps = get_desktop_applications()
        self._selected_index: int = -1

        self.viewport = Box(spacing=4, orientation="v")
        self.max_children = 4
        self.launch_handler = LauncherListsHandler(
            on_start=lambda *_: self.header.add_style_class("shine"),
            on_done=lambda *_: (
                self.post_viewport_arrange(),
                self.header.remove_style_class("shine"),
            ),
            on_slot_ready=self.on_slot_ready,
            on_launched=lambda *_: self.launched(),
            viewport=self.viewport,
        )

        self.header_icon = Image(icon_name="system-search-symbolic")
        self.header_entry = Entry(
            placeholder="Search...",
            style_classes="app-search-entry",
            h_expand=True,
            on_activate=self.on_entry_accept,
            on_changed=self.on_entry_changed,
        ).build(lambda entry, _: entry.connect("key-press-event", self.on_key_press))

        self.launch_handler.header_entry = self.header_entry

        self.header = Box(
            style_classes="app-search-header",
            spacing=8,
            orientation="h",
            children=[
                self.header_icon,
                self.header_entry,
            ],
        )

        self.scrolled_window = AnimatedScrollable(
            max_content_size=(280, 320),
            child=self.viewport,
            h_expand=True,
            v_expand=True,
            visible=False,
        )

        self.scrolled_clip = ClippingBox(
            style_classes="launcher-scroll-clip",
            children=self.scrolled_window,
            visible=False,
        )
        self.scrolled_window.connect("unmap", lambda: self.scrolled_clip.hide())

        self.children = self.header, self.scrolled_clip
        self.active_plugin = None

    def route_by_keyword(self, text: str) -> bool:
        stripped = text.lstrip()
        lower = stripped.lower()

        def starts(prefix: str) -> bool:
            return lower.startswith(prefix + " ") or lower == prefix

        for plugin in self.launch_handler.plugins.values():
            # Check if plugin has new interface
            keywords = getattr(plugin, "keywords", [])
            for keyword in keywords:
                if starts(keyword):
                    arg = stripped[len(keyword) :].lstrip()

                    # Update UI
                    if hasattr(plugin, "icon"):
                        self.header_icon.set_from_icon_name(plugin.icon)

                    # Handle plugins that need full viewport clear (e.g. search queries)
                    if getattr(plugin, "full_viewport_clear", False):
                        self.launch_handler.clear_viewport()
                        self.scrolled_window.animate_size(0)
                        self.scrolled_window.hide()
                        self.scrolled_clip.hide()

                    # Activate plugin
                    if self.active_plugin != plugin:
                        if self.active_plugin and hasattr(
                            self.active_plugin, "on_deactivate"
                        ):
                            self.active_plugin.on_deactivate()
                        self.active_plugin = plugin
                        if hasattr(plugin, "on_activate"):
                            plugin.on_activate()

                    # Call search
                    if hasattr(plugin, "on_search"):
                        plugin.on_search(arg)

                    return True

        # No keyword matched
        if self.active_plugin:
            if hasattr(self.active_plugin, "on_deactivate"):
                self.active_plugin.on_deactivate()
            self.active_plugin = None

        return False

    def handle_external(self, command: str, text: str = "") -> bool:
        # 1. Try direct plugin name match
        plugin = self.launch_handler.plugins.get(command)
        if plugin:
            if hasattr(plugin, "handle_external"):
                plugin.handle_external(command, text)
                return True
            return False

        # 2. Try keyword match
        for plugin in self.launch_handler.plugins.values():
            keywords = getattr(plugin, "keywords", [])
            if command in keywords and hasattr(plugin, "handle_external"):
                plugin.handle_external(command, text)
                return True

        return False

    def _set_entry_password_mode(self, enabled: bool):
        """Set entry widget to password mode (show asterisks) or normal mode"""
        if self.header_entry:
            if hasattr(self.header_entry, "set_visibility") or isinstance(
                self.header_entry, Gtk.Entry
            ):
                self.header_entry.set_visibility(not enabled)
                if enabled:
                    self.header_entry.set_invisible_char("*")
            else:
                try:
                    gtk_widget = getattr(self.header_entry, "widget", self.header_entry)
                    if isinstance(gtk_widget, Gtk.Entry):
                        gtk_widget.set_visibility(not enabled)
                        if enabled:
                            gtk_widget.set_invisible_char("*")
                except (AttributeError, TypeError):
                    pass

    def _is_typing_password_in_add_command(self, text: str) -> bool:
        """Check if user is typing the password field in an 'add' command"""
        text_stripped = text.strip()
        text_lower = text_stripped.lower()

        is_pass_mode = text_lower.startswith("pass ") or text_lower == "pass"
        has_add_command = "add " in text_lower

        if not has_add_command:
            return False

        if is_pass_mode:
            add_index = text_lower.find("add ")
            if add_index == -1:
                return False
            rest = text_stripped[add_index + 4 :].strip()
        else:
            if not text_lower.startswith("add "):
                return False
            rest = text_stripped[4:].strip()

        if not rest:
            return False

        parts = rest.split(None, 2)
        return len(parts) == 3

    @debounce(200)
    def on_entry_changed(self, entry: Entry, *_):
        if getattr(entry, "_ignore_change", False):
            entry._ignore_change = False
            return

        text = entry.get_text()
        self._selected_index = -1

        # Check if any plugin is in password mode
        for plugin in self.launch_handler.plugins.values():
            if getattr(plugin, "is_password_mode", False):
                self.launch_handler.stop()
                self.header_icon.set_from_icon_name("password-manager")
                self._set_entry_password_mode(True)
                self.launch_handler.clear_viewport()
                self.scrolled_window.hide()
                self.scrolled_clip.hide()
                return

        # Check if user is typing password in "add" command
        if self._is_typing_password_in_add_command(text):
            self._set_entry_password_mode(True)
        else:
            self._set_entry_password_mode(False)

        self.launch_handler.stop()
        self.launch_handler.clear_viewport()

        # Try to route to a plugin
        if self.route_by_keyword(text):
            return

        # Default: Application Search
        self.header_icon.set_from_icon_name("system-search-symbolic")
        app_plugin = self.launch_handler.plugins.get("application")
        if app_plugin:
            app_plugin.query_applications(text)
        return

    def post_viewport_children(self):
        if (
            new_hight := get_children_height_limit(self.viewport, self.max_children)
        ) < 1:
            self.scrolled_window.animate_size(0)
            return False

        self.scrolled_clip.show()
        self.scrolled_window.show()
        self.scrolled_window.animate_size(new_hight)

        for i, slot in enumerate(self.viewport.children, start=1):
            if i > 8:
                break
            slot.set_style(f"animation-duration: {round(i * 300)}ms;")
            slot.add_style_class("shine")

    def post_viewport_arrange(self, *_):
        if len(self.viewport.children) < 1:
            self.remove_style_class("overshoot")
        elif "overshoot" not in self.style_classes:
            add_style_class_lazy(self, "overshoot")
        self.post_viewport_children()
        # Auto-select the first child if results are available
        if self.viewport.children:
            self.set_selected_index(0)
        return False

    def on_slot_ready(self, _, button: Button, mode: str):
        self.viewport.add(button)
        button.connect("enter-notify-event", self.on_slot_enter)

    def on_slot_enter(self, button, event):
        children = self.viewport.children
        if button in children:
            self.set_selected_index(children.index(button))

    def on_entry_accept(self, entry: Entry, *_):
        text = entry.get_text()
        # Generic password submission handling
        for plugin in self.launch_handler.plugins.values():
            if getattr(plugin, "is_password_mode", False):
                pwd = entry.get_text()
                if hasattr(plugin, "submit_password") and pwd.strip():
                    plugin.submit_password(pwd)
                elif hasattr(plugin, "cancel_password"):
                    plugin.cancel_password()

                self.launch_handler.stop()
                self.launch_handler.clear_viewport()
                self.scrolled_window.animate_size(0)
                self.scrolled_window.hide()
                self.scrolled_clip.hide()
                self.header_icon.set_from_icon_name("system-search-symbolic")
                self._set_entry_password_mode(False)
                entry._ignore_change = True
                entry.set_text("")
                return

        if self._selected_index >= 0 and self._selected_index < len(
            self.viewport.children
        ):
            selected_widget = self.viewport.children[self._selected_index]
            if isinstance(selected_widget, Button):
                selected_widget.clicked()
                return

        if self.active_plugin:
            self.active_plugin.on_submit(text)
            entry.set_text("")
            return

        self._set_entry_password_mode(False)
        self.header_icon.set_from_icon_name("system-search-symbolic")
        app_plugin = self.launch_handler.plugins.get("application")
        if app_plugin:
            app_plugin.query_applications(entry.get_text())
        return

    def set_selected_index(self, index: int):
        children = self.viewport.children
        if not children:
            self._selected_index = -1
            return

        # Clean old selection
        if self._selected_index >= 0 and self._selected_index < len(children):
            children[self._selected_index].remove_style_class("selected")

        # Set new selection
        self._selected_index = index % len(children)
        selected_widget = children[self._selected_index]
        selected_widget.add_style_class("selected")

        # Scroll to selected item
        adj = self.scrolled_window.get_vadjustment()
        alloc = selected_widget.get_allocation()
        res = selected_widget.translate_coordinates(self.viewport, 0, 0)
        if res:
            y = res[1] if len(res) == 2 else res[2]
            top = y
            bottom = y + alloc.height
            value = adj.get_value()
            page_size = adj.get_page_size()
            if top < value:
                adj.set_value(top)
            elif bottom > value + page_size:
                adj.set_value(bottom - page_size)

    def on_key_press(self, entry, event):
        keyval = event.keyval
        if keyval == Gdk.KEY_Up or keyval == Gdk.KEY_ISO_Left_Tab:
            self.set_selected_index(self._selected_index - 1)
            return True
        elif keyval == Gdk.KEY_Down or keyval == Gdk.KEY_Tab:
            self.set_selected_index(self._selected_index + 1)
            return True
        return False


class LauncherWindow(Window):
    def __init__(self, **kwargs):
        self.launcher_box = Launcher(
            on_launched=lambda: self.close_launcher(), size=(460, -1)
        )
        super().__init__(
            name="launcher-window",
            title="fabric-launcher",
            anchor="top",
            margin="80px 0px 0px 0px",
            keyboard_mode="exclusive",
            child=self.launcher_box,
            visible=False,
            all_visible=False,
            **kwargs,
        )

        self.build()
        self.add_keybinding("Escape", lambda *_: self.close_launcher())

    def close_launcher(self):
        self.launcher_box.header_entry.set_text("")
        self.launcher_box.launch_handler.stop()
        self.launcher_box.launch_handler.clear_viewport()
        self.launcher_box.scrolled_window.animate_size(0)
        self.launcher_box.scrolled_window.hide()
        self.launcher_box.scrolled_clip.hide()
        self.launcher_box.header_icon.set_from_icon_name("system-search-symbolic")
        self.launcher_box._set_entry_password_mode(False)
        self.hide()

    def toggle(
        self, command: str | None = None, text: str = "", external: bool = False
    ):
        if external:
            full = f"{command or ''} {text or ''}".strip()
            if full:
                cmd, rest = (full.split(" ", 1) + [""])[:2]
                self.launcher_box.handle_external(cmd.strip(), rest.strip())
                return

        if self.get_visible():
            self.close_launcher()
            return

        cmd = (command or "").strip()
        txt = (text or "").strip()

        parts = [p for p in [cmd, txt] if p]
        prefill = " ".join(parts)

        if cmd and not txt:
            prefill += " "

        # Reset any pending password prompts on open
        password_plugin = self.launcher_box.launch_handler.plugins.get("password")
        if password_plugin and hasattr(password_plugin, "reset_prompt_state"):
            password_plugin.reset_prompt_state()

        self.launcher_box.header_entry.set_text(prefill)
        self.launcher_box._set_entry_password_mode(False)

        self.show_all()
        self.launcher_box.header_entry.grab_focus()
        self.launcher_box.header_entry.set_position(-1)
