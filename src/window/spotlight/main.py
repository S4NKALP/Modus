import gc
import os

from fabric.core import Signal
from fabric.utils import Gdk, GLib
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.wayland import WaylandWindow as Window

from shared.widgets.clipping_box import ClippingBox
from shared.window.animated_scrollwindow import AnimatedScrollable
from utils.debounce import debounce
from utils.functions import get_children_height_limit
from window.spotlight.api.context import PluginContext
from window.spotlight.api.result import SearchResult
from window.spotlight.core.loader import PluginLoader
from window.spotlight.core.manager import PluginManager
from window.spotlight.core.registry import PluginRegistry
from window.spotlight.core.search import SearchPipeline


class PluginService:
    """Owns plugin lifecycle and search pipeline. Plain class, no GObject."""

    def __init__(self):
        builtin_dir = os.path.join(os.path.dirname(__file__), "plugins")
        context = PluginContext()
        loader = PluginLoader(builtin_dir)
        registry = PluginRegistry()
        self.manager = PluginManager(loader, registry, context)
        self.pipeline = SearchPipeline(self.manager)
        self.manager.load_all()

    def stop(self):
        self.pipeline.cancel()
        self.manager.stop_all()

    def get_plugin(self, plugin_id: str):
        return self.manager.get_plugin(plugin_id)

    def get_all_plugins(self):
        return {e.id: e for e in self.manager.registry.get_enabled()}


class Spotlight(Box):
    @Signal
    def launched(self): ...

    def __init__(self, **kwargs):
        super().__init__(name="spotlight", spacing=4, orientation="v", **kwargs)

        self._selected_index: int = -1
        self._current_results: list[SearchResult] = []
        self._active_plugin_entry = None
        self._refresh_timer_id: int = 0
        self._result_widgets: dict[str, Button] = {}

        self.viewport = Box(spacing=4, orientation="v")
        self.max_children = 4

        self.plugin_service = PluginService()

        self.header_icon = Image(icon_name="system-search-symbolic")
        self.header_entry = Entry(
            placeholder="Search...",
            style_classes="app-search-entry",
            h_expand=True,
            on_activate=self.on_entry_accept,
            on_changed=self.on_entry_changed,
        ).build(lambda entry, _: entry.connect("key-press-event", self.on_key_press))

        self.header = Box(
            style_classes="app-search-header",
            spacing=8,
            orientation="h",
            children=[self.header_icon, self.header_entry],
        )

        self.scrolled_window = AnimatedScrollable(
            max_content_size=(280, 320),
            child=self.viewport,
            h_expand=True,
            v_expand=True,
            visible=False,
            animate=False,
        )

        self.scrolled_clip = ClippingBox(
            style_classes="spotlight-scroll-clip",
            children=self.scrolled_window,
            visible=False,
        )
        self.scrolled_window.connect("unmap", lambda: self.scrolled_clip.hide())

        self.children = self.header, self.scrolled_clip

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    @debounce(200)
    def on_entry_changed(self, entry: Entry, *_):
        if getattr(entry, "_ignore_change", False):
            entry._ignore_change = False
            return

        text = entry.get_text()
        self._selected_index = -1

        keyword_entry, _kw, _remaining = self.plugin_service.pipeline._route(text)
        if keyword_entry:
            self._activate_keyword_plugin(keyword_entry, _kw, _remaining)
            self.plugin_service.pipeline.search_single(
                keyword_entry, text, self._on_search_results
            )
            return

        self._deactivate_keyword_plugin()

        if not text.strip():
            self._clear_viewport()
            self.header_icon.set_from_icon_name("system-search-symbolic")
            return

        for pe in self.plugin_service.manager.registry.get_searchable():
            inst = pe.instance
            if inst and inst.detect(text):
                self.header_icon.set_from_icon_name(
                    getattr(inst, "icon", "") or "system-search-symbolic"
                )
                self.plugin_service.pipeline.search(text, self._on_search_results)
                return

        self.header_icon.set_from_icon_name("system-search-symbolic")
        self.plugin_service.pipeline.search(text, self._on_search_results)

    def _activate_keyword_plugin(self, entry, keyword: str, query: str):
        inst = entry.instance
        if not inst:
            return

        if self._active_plugin_entry and self._active_plugin_entry is not entry:
            old = self._active_plugin_entry.instance
            if old:
                old.on_deactivate()

        self._active_plugin_entry = entry

        keyword_icons = getattr(inst, "keyword_icons", {})
        icon_name = (
            keyword_icons.get(keyword, getattr(inst, "icon", ""))
            or "system-search-symbolic"
        )
        self.header_icon.set_from_icon_name(icon_name)

        if getattr(inst, "full_viewport_clear", False):
            self._clear_viewport()
            self.scrolled_window.animate_size(0)
            self.scrolled_window.hide()
            self.scrolled_clip.hide()

        inst.on_activate(self.update_result_subtitle)
        self._start_refresh_timer(entry, query)

    def _deactivate_keyword_plugin(self):
        self._stop_refresh_timer()
        if self._active_plugin_entry:
            inst = self._active_plugin_entry.instance
            if inst:
                inst.on_deactivate()
            self._active_plugin_entry = None

    def _start_refresh_timer(self, entry, query: str):
        self._stop_refresh_timer()
        inst = entry.instance
        interval = getattr(inst, "refresh_interval", 0) if inst else 0
        if interval <= 0:
            return

        def _tick():
            if self._active_plugin_entry is not entry:
                return False
            inst = entry.instance
            if not inst:
                return False
            inst.on_timer_tick()
            return True

        self._refresh_timer_id = GLib.timeout_add(interval, _tick)

    def _stop_refresh_timer(self):
        if self._refresh_timer_id:
            GLib.source_remove(self._refresh_timer_id)
            self._refresh_timer_id = 0

    def _auto_start_refresh_timer(self, results: list[SearchResult]):
        for result in results:
            if not result.plugin_id:
                continue
            entry = self.plugin_service.manager.registry.get(result.plugin_id)
            if not entry:
                continue
            inst = entry.instance
            if not inst:
                continue
            interval = getattr(inst, "refresh_interval", 0)
            if interval > 0:
                if self._active_plugin_entry is entry and self._refresh_timer_id:
                    return
                if self._active_plugin_entry and self._active_plugin_entry is not entry:
                    old = self._active_plugin_entry.instance
                    if old:
                        old.on_deactivate()
                self._active_plugin_entry = entry
                inst.on_activate(self.update_result_subtitle)
                self._start_refresh_timer(entry, "")
                return
        self._auto_stop_refresh_timer()

    def _auto_stop_refresh_timer(self):
        if self._active_plugin_entry:
            inst = self._active_plugin_entry.instance
            interval = getattr(inst, "refresh_interval", 0) if inst else 0
            if interval <= 0:
                self._deactivate_keyword_plugin()

    def _on_search_results(self, results: list[SearchResult]):
        self._clear_viewport()
        self._current_results = results

        if not results:
            self._auto_stop_refresh_timer()
            self._post_arrange()
            return

        self._auto_start_refresh_timer(results)

        for result in results:
            widget = self._render_result(result)
            self._result_widgets[result.id] = widget
            self.viewport.add(widget)
            widget.connect("enter-notify-event", self.on_slot_enter)

        self._post_arrange()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render_result(self, result: SearchResult) -> Button:
        rt = result.render_type
        if rt == "app":
            return self._render_app(result)
        if rt == "calc":
            return self._render_calc(result)
        if rt == "emoji":
            return self._render_emoji(result)
        if rt == "power":
            return self._render_power(result)
        if rt == "wallpaper":
            return self._render_wallpaper(result)
        if rt == "clipboard_text":
            return self._render_clipboard_text(result)
        if rt == "clipboard_image":
            return self._render_clipboard_image(result)
        return self._render_default(result)

    def _render_app(self, r: SearchResult) -> Button:
        app = r.metadata.get("desktop_app")
        children = []
        if app:
            pixbuf = app.get_icon_pixbuf()
            if pixbuf:
                children.append(Image(pixbuf=pixbuf, h_align="start", size=32))
        title_box = Box(
            orientation="v",
            children=[
                Label(
                    label=r.title or "Unknown",
                    v_align="start",
                    h_align="start",
                    style_classes="app-title",
                )
            ],
        )
        if r.subtitle:
            title_box.add(
                Label(
                    label=r.subtitle,
                    max_chars_width=42,
                    ellipsization="middle",
                    justification="center",
                    style_classes="app-description",
                    v_align="start",
                    h_align="start",
                )
            )
        children.append(title_box)

        return Button(
            style_classes="app-slot",
            child=Box(orientation="h", spacing=12, children=children),
            tooltip_text=r.subtitle,
            on_clicked=lambda *_: self._activate_result(r),
        )

    def _render_calc(self, r: SearchResult) -> Button:
        return Button(
            style_classes="app-slot calc-result",
            child=Box(
                orientation="h",
                spacing=12,
                children=[
                    Image(
                        icon_name=r.icon_name or "accessories-calculator-symbolic",
                        h_align="start",
                        size=32,
                    ),
                    Box(
                        orientation="v",
                        children=[
                            Label(
                                label=r.title,
                                style_classes="calc-expression",
                                h_align="start",
                            ),
                            Label(
                                label=r.subtitle,
                                style_classes="calc-result-text",
                                h_align="start",
                            ),
                        ],
                    ),
                ],
            ),
            on_clicked=lambda *_: self._activate_result(r),
        )

    def _render_emoji(self, r: SearchResult) -> Button:
        emoji_char = r.metadata.get("emoji", r.title)
        keyword_str = ", ".join(r.metadata.get("keywords", [])[:3])
        return Button(
            style_classes="app-slot emoji-slot",
            child=Box(
                orientation="h",
                spacing=12,
                children=[
                    Label(
                        label=emoji_char,
                        style_classes="emoji-char",
                        h_align="start",
                        v_align="center",
                    ),
                    Box(
                        orientation="v",
                        children=[
                            Label(
                                label=r.subtitle,
                                style_classes="emoji-name",
                                h_align="start",
                                v_align="start",
                            ),
                            Label(
                                label=keyword_str,
                                style_classes="emoji-keywords",
                                h_align="start",
                                v_align="start",
                            ),
                        ],
                    ),
                ],
            ),
            tooltip_text=f"Click to copy {emoji_char}",
            on_clicked=lambda *_: self._activate_result(r),
        )

    def _render_power(self, r: SearchResult) -> Button:
        return Button(
            style_classes="app-slot power-menu-slot",
            child=Box(
                orientation="h",
                spacing=12,
                children=[
                    Image(icon_name=r.icon_name, h_align="start", size=32),
                    Box(
                        orientation="v",
                        children=[
                            Label(
                                label=r.title,
                                style_classes="power-menu-name",
                                h_align="start",
                                v_align="start",
                            ),
                            Label(
                                label=r.subtitle,
                                style_classes="power-menu-description",
                                h_align="start",
                                v_align="start",
                            ),
                        ],
                    ),
                ],
            ),
            tooltip_text=f"Click to {r.title.lower()} the system",
            on_clicked=lambda *_: self._activate_result(r),
        )

    def _render_wallpaper(self, r: SearchResult) -> Button:
        thumb = r.metadata.get("thumbnail_path", "")
        child_widget = Box(h_expand=True, v_expand=True)
        if thumb and os.path.exists(thumb):
            child_widget = (
                Box(h_expand=True, v_expand=True)
                .build()
                .set_style(f"background-image: url('file://{thumb}');", compile=False)
                .unwrap()
            )
        return Button(
            style_classes="app-slot wallpaper",
            child=child_widget,
            on_clicked=lambda *_: self._activate_result(r),
        )

    def _render_clipboard_text(self, r: SearchResult) -> Button:
        display = r.title
        return Button(
            style_classes="app-slot clipboard-text",
            child=Box(
                orientation="h",
                children=[
                    Label(
                        label=display,
                        style_classes="clipboard-content",
                        h_align="center",
                        v_align="center",
                        max_chars_width=40,
                        ellipsization="end",
                    )
                ],
            ),
            tooltip_text=r.subtitle,
            on_clicked=lambda *_: self._activate_result(r),
        )

    def _render_clipboard_image(self, r: SearchResult) -> Button:
        img_path = r.metadata.get("image_path", "")
        child_widget = Box(
            orientation="h",
            children=[
                Label(
                    label="Image",
                    style_classes="clipboard-content",
                    h_align="center",
                    v_align="center",
                )
            ],
        )
        if img_path and os.path.exists(img_path):
            child_widget = (
                Box(h_expand=True, v_expand=True)
                .build()
                .set_style(
                    f"background-image: url('file://{img_path}');",
                    compile=False,
                )
                .unwrap()
            )
        return Button(
            style_classes="app-slot wallpaper clipboard-image",
            child=child_widget,
            on_clicked=lambda *_: self._activate_result(r),
        )

    def _render_default(self, r: SearchResult) -> Button:
        children = []
        if r.icon_name:
            children.append(Image(icon_name=r.icon_name, h_align="start", size=32))
        title_box = Box(
            orientation="v",
            children=[
                Label(
                    label=r.title,
                    style_classes="app-title",
                    h_align="start",
                    v_align="start",
                )
            ],
        )
        if r.subtitle:
            title_box.add(
                Label(
                    label=r.subtitle,
                    style_classes="app-description",
                    h_align="start",
                    v_align="start",
                )
            )
        children.append(title_box)

        return Button(
            style_classes="app-slot",
            child=Box(orientation="h", spacing=12, children=children),
            on_clicked=lambda *_: self._activate_result(r),
        )

    def _activate_result(self, result: SearchResult):
        if result.action:
            result.action()
        self.launched()

    # ------------------------------------------------------------------
    # Viewport management
    # ------------------------------------------------------------------

    def _clear_viewport(self):
        old_results = self._current_results
        self._current_results = []
        self._result_widgets.clear()
        for child in self.viewport.children:
            try:
                child.disconnect_by_func(self.on_slot_enter)
            except (TypeError, ValueError):
                pass
            self.viewport.remove(child)
            child.destroy()
        del old_results

    def update_result_subtitle(self, result_id: str, text: str) -> None:
        """Update subtitle label of a rendered result in-place (no re-render)."""
        widget = self._result_widgets.get(result_id)
        if not widget:
            return
        child = widget.get_child()
        if not child:
            return
        # Walk: Button → main Box → title_box (last Box) → subtitle Label (2nd)
        from fabric.widgets.box import Box
        from fabric.widgets.label import Label

        boxes = [c for c in child.get_children() if isinstance(c, Box)]
        if not boxes:
            return
        title_box = boxes[-1]
        labels = [c for c in title_box.get_children() if isinstance(c, Label)]
        if len(labels) >= 2:
            labels[1].set_text(text)

    def _post_arrange(self):
        new_height = get_children_height_limit(self.viewport, self.max_children)
        if new_height < 1:
            self.scrolled_window.animate_size(0)
            self.scrolled_clip.hide()
            self.scrolled_window.hide()
            return

        self.scrolled_clip.show()
        self.scrolled_window.show()
        self.scrolled_window.animate_size(new_height)

        for i, slot in enumerate(self.viewport.children, start=1):
            if i > 8:
                break
            slot.set_style(f"animation-duration: {round(i * 300)}ms;")
            slot.add_style_class("shine")

        if self.viewport.children:
            self.set_selected_index(0)

    # ------------------------------------------------------------------
    # Selection & keyboard
    # ------------------------------------------------------------------

    def on_slot_enter(self, button, event):
        children = self.viewport.children
        if button in children:
            self.set_selected_index(children.index(button))

    def set_selected_index(self, index: int):
        children = self.viewport.children
        if not children:
            self._selected_index = -1
            return

        if 0 <= self._selected_index < len(children):
            children[self._selected_index].remove_style_class("selected")

        self._selected_index = index % len(children)
        selected = children[self._selected_index]
        selected.add_style_class("selected")

        adj = self.scrolled_window.get_vadjustment()
        alloc = selected.get_allocation()
        res = selected.translate_coordinates(self.viewport, 0, 0)
        if res:
            y = res[1] if len(res) == 2 else res[2]
            if y < adj.get_value():
                adj.set_value(y)
            elif y + alloc.height > adj.get_value() + adj.get_page_size():
                adj.set_value(y + alloc.height - adj.get_page_size())

    def on_key_press(self, entry, event):
        keyval = event.keyval
        if keyval == Gdk.KEY_Up or keyval == Gdk.KEY_ISO_Left_Tab:
            self.set_selected_index(self._selected_index - 1)
            return True
        if keyval == Gdk.KEY_Down or keyval == Gdk.KEY_Tab:
            self.set_selected_index(self._selected_index + 1)
            return True
        return False

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------

    def on_entry_accept(self, entry: Entry, *_):
        if 0 <= self._selected_index < len(self.viewport.children):
            widget = self.viewport.children[self._selected_index]
            if isinstance(widget, Button):
                widget.clicked()
                return

        if self._active_plugin_entry:
            inst = self._active_plugin_entry.instance
            if inst:
                inst.on_submit(entry.get_text())
            entry.set_text("")
            return

        if self._current_results:
            self._activate_result(self._current_results[0])

    # ------------------------------------------------------------------
    # External commands
    # ------------------------------------------------------------------

    def handle_external(self, command: str, text: str = "") -> bool:
        if command == "deep_reload" and text:
            return self.plugin_service.manager.deep_reload(text.strip())

        plugin = self.plugin_service.get_plugin(command)
        if plugin and hasattr(plugin, "handle_external"):
            plugin.handle_external(command, text)
            return True

        for pe in self.plugin_service.manager.registry.get_enabled():
            inst = pe.instance
            if inst and command in getattr(inst, "keywords", []):
                if hasattr(inst, "handle_external"):
                    inst.handle_external(command, text)
                    return True

        return False


class SpotlightWindow(Window):
    def __init__(self, **kwargs):
        self.spotlight_box = Spotlight(
            on_launched=lambda: self.close_spotlight(), size=(460, -1)
        )
        super().__init__(
            name="spotlight-window",
            title="fabric-spotlight",
            anchor="top",
            margin="80px 0px 0px 0px",
            keyboard_mode="on-demand",
            child=self.spotlight_box,
            visible=False,
            all_visible=False,
            **kwargs,
        )

        self.build()
        self.add_keybinding("Escape", lambda *_: self.close_spotlight())

    def close_spotlight(self):
        self.spotlight_box.plugin_service.pipeline.cancel()

        debounce_id = getattr(
            self.spotlight_box, "_debounce_timer_on_entry_changed", None
        )
        if debounce_id:
            GLib.source_remove(debounce_id)
            self.spotlight_box._debounce_timer_on_entry_changed = 0
        self.spotlight_box._stop_refresh_timer()

        self.spotlight_box.header_entry.set_text("")
        self.spotlight_box._clear_viewport()
        self.spotlight_box.scrolled_window.animate_size(0)
        self.spotlight_box.scrolled_window.hide()
        self.spotlight_box.scrolled_clip.hide()
        self.spotlight_box.header_icon.set_from_icon_name("system-search-symbolic")
        self.spotlight_box._deactivate_keyword_plugin()
        self.spotlight_box.plugin_service.manager.release_memory_all()
        gc.collect()
        self.hide()

    def toggle(
        self, command: str | None = None, text: str = "", external: bool = False
    ):
        if external:
            full = f"{command or ''} {text or ''}".strip()
            if full:
                cmd, rest = ([*full.split(" ", 1), ""])[:2]
                self.spotlight_box.handle_external(cmd.strip(), rest.strip())
                return

        if self.get_visible():
            self.close_spotlight()
            return

        cmd = (command or "").strip()
        txt = (text or "").strip()

        parts = [p for p in [cmd, txt] if p]
        prefill = " ".join(parts)

        if cmd and not txt:
            prefill += " "

        self.spotlight_box.header_entry.set_text(prefill)

        self.show_all()
        self.spotlight_box.scrolled_clip.hide()
        self.spotlight_box.scrolled_window.hide()
        self.spotlight_box.header_entry.grab_focus()
        self.spotlight_box.header_entry.set_position(-1)
