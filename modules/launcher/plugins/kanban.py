"""
Kanban plugin for the launcher.
Provides a kanban board interface for task management.
"""

import json
import os
from pathlib import Path
from typing import List

import cairo
import gi
import utils.icons as icons
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow
from gi.repository import Gdk, GLib, GObject, Gtk
from modules.launcher.plugin_base import PluginBase
from modules.launcher.result import Result

gi.require_version("Gtk", "3.0")


def createSurfaceFromWidget(widget: Gtk.Widget) -> cairo.ImageSurface:
    alloc = widget.get_allocation()
    surface = cairo.ImageSurface(cairo.Format.ARGB32, alloc.width, alloc.height)
    cr = cairo.Context(surface)

    cr.set_source_rgba(0, 0, 0, 0)
    cr.rectangle(0, 0, alloc.width, alloc.height)
    cr.fill()
    widget.draw(cr)
    return surface


class InlineEditor(Gtk.Box):
    __gsignals__ = {
        "confirmed": (GObject.SignalFlags.RUN_LAST, None, (str,)),
        "canceled": (GObject.SignalFlags.RUN_LAST, None, ()),
    }

    def __init__(self, initial_text=""):
        super().__init__(name="inline-editor", spacing=4)

        self.text_view = Gtk.TextView()
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        buffer = self.text_view.get_buffer()
        buffer.set_text(initial_text)

        self.text_view.connect("key-press-event", self.on_key_press)

        # Create labels for buttons
        confirm_label = Gtk.Label()
        confirm_label.set_markup(icons.accept)
        confirm_label.set_name("kanban-btn-label")

        cancel_label = Gtk.Label()
        cancel_label.set_markup(icons.cancel)
        cancel_label.set_name("kanban-btn-neg")

        confirm_btn = Gtk.Button()
        confirm_btn.set_name("kanban-btn")
        confirm_btn.add(confirm_label)
        confirm_btn.connect("clicked", self.on_confirm)
        confirm_btn.get_style_context().add_class("flat")

        cancel_btn = Gtk.Button()
        cancel_btn.set_name("kanban-btn")
        cancel_btn.add(cancel_label)
        cancel_btn.connect("clicked", self.on_cancel)
        cancel_btn.get_style_context().add_class("flat")

        sw = Gtk.ScrolledWindow()
        sw.set_name("scrolled-window")
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.set_min_content_height(50)
        sw.add(self.text_view)

        self.button_box = Gtk.Box(spacing=4)
        self.button_box.pack_start(confirm_btn, False, False, 0)
        self.button_box.pack_start(cancel_btn, False, False, 0)

        self.center_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.center_box.set_halign(Gtk.Align.CENTER)
        self.center_box.pack_start(self.button_box, False, False, 0)

        self.pack_start(sw, True, True, 0)
        self.pack_start(self.center_box, False, False, 0)
        self.show_all()

    def on_confirm(self, widget):
        buffer = self.text_view.get_buffer()
        start, end = buffer.get_bounds()
        text = buffer.get_text(start, end, True).strip()
        if text:
            self.emit("confirmed", text)
        else:
            self.emit("canceled")

    def on_cancel(self, widget):
        self.emit("canceled")

    def on_key_press(self, widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.emit("canceled")
            return True

        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            state = event.get_state()
            if state & Gdk.ModifierType.SHIFT_MASK:
                buffer = self.text_view.get_buffer()
                cursor_iter = buffer.get_iter_at_mark(buffer.get_insert())
                buffer.insert(cursor_iter, "\n")
                return True
            else:
                self.on_confirm(widget)
                return True
        return False


class KanbanNote(Gtk.EventBox):
    __gsignals__ = {
        "changed": (GObject.SignalFlags.RUN_LAST, None, ()),
    }

    def __init__(self, text):
        super().__init__()
        self.text = text

        self.setup_ui()
        self.setup_dnd()
        self.connect("button-press-event", self.on_button_press)

    def setup_ui(self):
        self.box = Gtk.Box(name="kanban-note", spacing=4)
        self.label = Gtk.Label(label=self.text)
        self.label.set_line_wrap(True)

        self.label.set_line_wrap_mode(Gtk.WrapMode.WORD)

        self.delete_btn = Gtk.Button(
            name="kanban-btn", child=Label(name="kanban-btn-neg", markup=icons.trash)
        )
        self.delete_btn.connect("clicked", self.on_delete_clicked)

        self.center_btn = CenterBox(orientation="v", start_children=[self.delete_btn])

        self.box.pack_start(self.label, True, True, 0)
        self.box.pack_start(self.center_btn, False, False, 0)
        self.add(self.box)
        self.show_all()

    def setup_dnd(self):
        self.drag_source_set(
            Gdk.ModifierType.BUTTON1_MASK,
            [Gtk.TargetEntry.new("UTF8_STRING", Gtk.TargetFlags.SAME_APP, 0)],
            Gdk.DragAction.MOVE,
        )
        self.connect("drag-data-get", self.on_drag_data_get)
        self.connect("drag-data-delete", self.on_drag_data_delete)

        self.connect("drag-begin", self.on_drag_begin)

    def on_button_press(self, widget, event):
        if event.type != Gdk.EventType._2BUTTON_PRESS:
            return True
        self.start_edit()
        return False

    def on_drag_begin(self, widget, context):
        surface = createSurfaceFromWidget(self)
        Gtk.drag_set_icon_surface(context, surface)

    def on_drag_data_get(self, widget, drag_context, data, info, time):
        data.set_text(self.label.get_text(), -1)

    def on_drag_data_delete(self, widget, drag_context):
        self.get_parent().destroy()

    def on_delete_clicked(self, button):
        self.get_parent().destroy()

    def start_edit(self):
        row = self.get_parent()
        editor = InlineEditor(self.label.get_text())

        def on_confirmed(editor, text):
            self.label.set_text(text)
            # Ensure editor is properly removed before adding self back
            if editor.get_parent():
                editor.get_parent().remove(editor)
            if not self.get_parent():
                row.add(self)
            row.show_all()
            self.emit("changed")

        def on_canceled(editor):
            # Ensure editor is properly removed before adding self back
            if editor.get_parent():
                editor.get_parent().remove(editor)
            if not self.get_parent():
                row.add(self)
            row.show_all()

        editor.connect("confirmed", on_confirmed)
        editor.connect("canceled", on_canceled)

        # Only remove self if it has a parent
        if self.get_parent():
            row.remove(self)
        row.add(editor)
        row.show_all()

        GLib.timeout_add(50, lambda: (editor.text_view.grab_focus(), False))


class KanbanColumn(Gtk.Frame):
    __gsignals__ = {
        "changed": (GObject.SignalFlags.RUN_LAST, None, ()),
    }

    def __init__(self, title):
        super().__init__(name="kanban-column")
        self.title = title
        self.setup_ui()
        self.setup_dnd()
        self.set_hexpand(True)
        self.set_vexpand(True)
        # Set size constraints for launcher compatibility
        self.set_size_request(-1, 150)  # Fixed height per column

    def setup_ui(self):
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)

        self.add_btn = Gtk.Button(
            name="kanban-btn-add",
            child=Label(name="kanban-btn-label", markup=icons.add),
        )
        header = CenterBox(
            name="kanban-header",
            center_children=[Label(name="column-header", label=self.title)],
            end_children=[self.add_btn],
        )
        self.box.pack_start(header, False, False, 0)

        self.add_btn.connect("clicked", self.on_add_clicked)

        self.scroller = ScrolledWindow(
            name="scrolled-window", propagate_height=False, propagate_width=False
        )
        self.scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroller.add(self.listbox)
        self.scroller.set_vexpand(True)

        self.box.pack_start(self.scroller, True, True, 0)
        self.box.pack_start(self.add_btn, False, False, 0)
        self.add(self.box)
        self.show_all()

    def setup_dnd(self):
        self.listbox.drag_dest_set(
            Gtk.DestDefaults.ALL,
            [Gtk.TargetEntry.new("UTF8_STRING", Gtk.TargetFlags.SAME_APP, 0)],
            Gdk.DragAction.MOVE,
        )

        self.listbox.connect("drag-data-received", self.on_drag_data_received)
        self.listbox.connect("drag-motion", self.on_drag_motion)
        self.listbox.connect("drag-leave", self.on_drag_leave)

    def on_add_clicked(self, button):
        editor = InlineEditor()
        row = Gtk.ListBoxRow(name="kanban-row")
        row.add(editor)
        self.listbox.add(row)
        self.listbox.show_all()
        editor.text_view.grab_focus()

        def on_confirmed(editor, text):
            note = KanbanNote(text)
            note.connect("changed", lambda x: self.emit("changed"))
            # Ensure editor is properly removed before adding note
            if editor.get_parent():
                editor.get_parent().remove(editor)
            row.add(note)
            self.listbox.show_all()
            self.emit("changed")

        def on_canceled(editor):
            row.destroy()

        def scroll_to_bottom():
            adj = self.scroller.get_vadjustment()
            adj.set_value(adj.get_upper())

        editor.connect("confirmed", on_confirmed)
        editor.connect("canceled", on_canceled)

        # ensure this is called after row is loaded
        GLib.idle_add(scroll_to_bottom)

    def add_note(self, text, suppress_signal=False):
        note = KanbanNote(text)
        note.connect("changed", lambda x: self.emit("changed"))
        row = Gtk.ListBoxRow(name="kanban-row")
        row.add(note)
        row.connect("destroy", lambda x: self.emit("changed"))
        self.listbox.add(row)
        self.listbox.show_all()
        if not suppress_signal:
            self.emit("changed")

    def get_notes(self):
        return [
            row.get_children()[0].label.get_text()
            for row in self.listbox.get_children()
            if isinstance(row.get_children()[0], KanbanNote)
        ]

    def clear_notes(self, suppress_signal=False):
        for row in self.listbox.get_children():
            row.destroy()
        if not suppress_signal:
            self.emit("changed")

    def on_drag_data_received(self, widget, drag_context, x, y, data, info, time):
        text = data.get_text()
        if text:
            row = self.listbox.get_row_at_y(y)
            new_note = KanbanNote(text)
            new_note.connect("changed", lambda x: self.emit("changed"))
            new_row = Gtk.ListBoxRow(name="kanban-row")
            new_row.add(new_note)
            new_row.connect("destroy", lambda x: self.emit("changed"))

            if row:
                self.listbox.insert(new_row, row.get_index())
            else:
                self.listbox.add(new_row)

            self.listbox.show_all()
            drag_context.finish(True, False, time)
            self.emit("changed")

    def on_drag_motion(self, widget, drag_context, x, y, time):
        Gdk.drag_status(drag_context, Gdk.DragAction.MOVE, time)
        return True

    def on_drag_leave(self, widget, drag_context, time):
        widget.get_parent().get_parent().drag_unhighlight()


class Kanban(Gtk.Box):
    STATE_FILE = Path(os.path.expanduser("~/.kanban.json"))

    def __init__(self):
        super().__init__(name="kanban", orientation=Gtk.Orientation.VERTICAL)

        # Set size constraints to fit within launcher
        self.set_size_request(-1, 500)  # Fixed height to fit in launcher
        self.set_vexpand(False)
        self.set_hexpand(True)

        # Make the widget focusable so it can receive key events
        self.set_can_focus(True)
        self.connect("key-press-event", self.on_key_press)

        # Store pending add text for Enter key handling
        self.pending_add_text = None

        # Add a hidden Entry widget so the launcher will let us handle Enter events
        from fabric.widgets.entry import Entry
        self.hidden_entry = Entry(name="kanban-hidden-entry")
        self.hidden_entry.set_size_request(1, 1)  # Make it tiny
        self.hidden_entry.set_opacity(0.0)  # Make it invisible
        self.hidden_entry.connect("activate", self.on_hidden_entry_activate)
        self.add(self.hidden_entry)

        self.grid = Gtk.Grid(
            column_spacing=4,
            column_homogeneous=True,
            row_spacing=4,
            row_homogeneous=True,
        )
        self.grid.set_vexpand(True)
        self.grid.set_hexpand(True)
        self.add(self.grid)

        self.columns = [
            KanbanColumn("To Do"),
            KanbanColumn("In Progress"),
            KanbanColumn("Done"),
        ]

        # Always use vertical layout (columns stacked vertically)
        for i, column in enumerate(self.columns):
            # Vertical layout - columns stacked on top of each other
            self.grid.attach(column, 0, i, 1, 1)
            column.connect("changed", lambda x: self.save_state())

        self.load_state()
        self.show_all()

    def on_key_press(self, widget, event):
        """Handle key press events for the kanban widget."""
        if event.keyval == Gdk.KEY_Return:
            if self.pending_add_text:
                self.columns[0].add_note(self.pending_add_text)
                self.save_state()
                self.pending_add_text = None
                return True
        return False

    def on_hidden_entry_activate(self, entry):
        """Handle activation of the hidden entry (Enter key from launcher)."""
        if self.pending_add_text:
            self.columns[0].add_note(self.pending_add_text)
            self.save_state()
            self.pending_add_text = None

    def set_pending_add_text(self, text):
        """Set the pending add text for Enter key handling."""
        self.pending_add_text = text
        # Don't grab focus - let the launcher manage focus
        # The launcher will find our hidden entry when Enter is pressed

    def save_state(self):
        state = {
            "columns": [
                {"title": col.title, "notes": col.get_notes()} for col in self.columns
            ]
        }
        try:
            with open(self.STATE_FILE, "w") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f"Error saving state: {e}")

    def load_state(self):
        try:
            with open(self.STATE_FILE, "r") as f:
                state = json.load(f)
                for col_data in state["columns"]:
                    for column in self.columns:
                        if column.title == col_data["title"]:
                            column.clear_notes(suppress_signal=True)
                            for note_text in col_data["notes"]:
                                column.add_note(note_text, suppress_signal=True)
                            break
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"Error loading state: {e}")


class KanbanPlugin(PluginBase):
    """
    Kanban board plugin for the launcher.
    Provides a kanban-style task management interface.
    """

    def __init__(self):
        super().__init__()
        self.display_name = "Kanban"
        self.description = "Kanban board for task management"
        self._current_widget = None
        self._pending_add_text = None

    def initialize(self):
        """Initialize the Kanban plugin."""
        self.set_triggers(["kanban", "kanban "])
        self.description = "Kanban board for task management. Use 'kanban add <text>' to quickly add tasks."

    def cleanup(self):
        """Cleanup the Kanban plugin."""
        if self._current_widget:
            # Properly destroy the current widget
            if self._current_widget.get_parent():
                self._current_widget.get_parent().remove(self._current_widget)
            self._current_widget.destroy()
            self._current_widget = None
        self._pending_add_text = None

    def query(self, query_string: str) -> List[Result]:
        """Process Kanban queries."""
        results = []

        # Only create a new widget if we don't have one
        if not self._current_widget:
            kanban_widget = Kanban()
            self._current_widget = kanban_widget
        else:
            kanban_widget = self._current_widget

        # Check if this is an "add" command and store it for Enter key handling
        if query_string.startswith("add "):
            # Extract the note text
            note_text = query_string[4:].strip()
            if note_text:
                # Store the pending add command in the widget
                kanban_widget.set_pending_add_text(note_text)
            else:
                kanban_widget.set_pending_add_text(None)
        else:
            kanban_widget.set_pending_add_text(None)

        # Always show the kanban board directly when triggered
        results.append(
            Result(
                title="Kanban Board",
                subtitle="Task management with kanban-style columns",
                icon_markup=icons.kanban,
                action=lambda: None,  # No action needed, widget handles Enter
                relevance=1.0,
                plugin_name=self.display_name,
                custom_widget=kanban_widget,
                data={"type": "kanban_board", "keep_launcher_open": True},
            )
        )

        return results
