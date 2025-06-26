import json
import os
from pathlib import Path
from typing import List

import cairo
import gi
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow
from gi.repository import Gdk, GLib, GObject, Gtk

import utils.icons as icons
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

        # Make focusable for keyboard events
        self.set_can_focus(True)

        self.setup_ui()
        self.setup_dnd()
        self.connect("button-press-event", self.on_button_press)
        self.connect("key-press-event", self.on_key_press)

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

    def on_key_press(self, widget, event):
        """Handle keyboard events for kanban notes."""
        from gi.repository import Gdk

        keyval = event.keyval

        # Enter or F2 - start editing
        if keyval in (Gdk.KEY_Return, Gdk.KEY_F2):
            self.start_edit()
            return True

        # Delete - remove note
        if keyval == Gdk.KEY_Delete:
            self.get_parent().destroy()
            return True

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

    __gsignals__ = {
        "todo-added": (GObject.SignalFlags.RUN_LAST, None, ()),
    }

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
        # Store pending command for Enter key handling
        self.pending_command = None

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
        from gi.repository import Gdk

        keyval = event.keyval

        # Enter - handle pending commands
        if keyval == Gdk.KEY_Return:
            if self.pending_command:
                command, text = self.pending_command
                if command == "add":
                    self.columns[0].add_note(text)
                    self.save_state()

                elif command == "move":
                    success = self._execute_move_command(text)
                    if success:
                        self.save_state()
                elif command == "done":
                    success = self._execute_done_command(text)
                    if success:
                        self.save_state()

                # Clear pending command and notify plugin to reset
                self.pending_command = None
                self.pending_add_text = None
                self.emit("todo-added")  # Reuse this signal for all commands
                return True
            elif self.pending_add_text:
                # Fallback for old add system
                self.columns[0].add_note(self.pending_add_text)
                self.save_state()
                self.pending_add_text = None
                # Notify plugin to reset to trigger
                self.emit("todo-added")
                return True

        # Ctrl+N - add new note to first column
        if keyval == Gdk.KEY_n and event.state & Gdk.ModifierType.CONTROL_MASK:
            self.columns[0].on_add_clicked(None)
            return True

        # Ctrl+1, Ctrl+2, Ctrl+3 - add note to specific column
        if event.state & Gdk.ModifierType.CONTROL_MASK:
            if keyval == Gdk.KEY_1 and len(self.columns) > 0:
                self.columns[0].on_add_clicked(None)
                return True
            elif keyval == Gdk.KEY_2 and len(self.columns) > 1:
                self.columns[1].on_add_clicked(None)
                return True
            elif keyval == Gdk.KEY_3 and len(self.columns) > 2:
                self.columns[2].on_add_clicked(None)
                return True

        return False

    def on_hidden_entry_activate(self, entry):
        """Handle activation of the hidden entry (Enter key from launcher)."""
        if self.pending_command:
            command, text = self.pending_command
            if command == "add":
                self.columns[0].add_note(text)
                self.save_state()
            elif command == "move":
                success = self._execute_move_command(text)
                if success:
                    self.save_state()
            elif command == "done":
                success = self._execute_done_command(text)
                if success:
                    self.save_state()

            # Clear pending command and notify plugin to reset
            self.pending_command = None
            self.pending_add_text = None
            self.emit("todo-added")  # Reuse this signal for all commands
        elif self.pending_add_text:
            # Fallback for old add system
            self.columns[0].add_note(self.pending_add_text)
            self.save_state()
            self.pending_add_text = None
            # Notify plugin to reset to trigger
            self.emit("todo-added")

    def set_pending_add_text(self, text):
        """Set the pending add text for Enter key handling."""
        self.pending_add_text = text
        # Don't grab focus - let the launcher manage focus
        # The launcher will find our hidden entry when Enter is pressed

    def _execute_move_command(self, todo_text: str) -> bool:
        """Execute move command within the widget."""
        search_text = todo_text.lower().strip()

        # Find todo across all columns
        for col_idx, column in enumerate(self.columns):
            notes = column.get_notes()
            for note_text in notes:
                if search_text in note_text.lower():
                    # Determine next column
                    if col_idx == 0:  # To Do -> In Progress
                        next_col_idx = 1
                        next_state = "In Progress"
                    elif col_idx == 1:  # In Progress -> Done
                        next_col_idx = 2
                        next_state = "Done"
                    else:  # Already in Done
                        return False

                    # Remove from current column
                    for row in column.listbox.get_children():
                        note_widget = row.get_children()[0]
                        if (
                            isinstance(note_widget, KanbanNote)
                            and note_widget.label.get_text() == note_text
                        ):
                            row.destroy()
                            break

                    # Add to next column
                    next_column = self.columns[next_col_idx]
                    next_column.add_note(note_text)
                    return True

        return False

    def _execute_done_command(self, todo_text: str) -> bool:
        """Execute done command within the widget."""
        search_text = todo_text.lower().strip()

        # Find todo across all columns (except Done)
        # Only To Do and In Progress
        for col_idx, column in enumerate(self.columns[:2]):
            notes = column.get_notes()
            for note_text in notes:
                if search_text in note_text.lower():
                    # Remove from current column
                    for row in column.listbox.get_children():
                        note_widget = row.get_children()[0]
                        if (
                            isinstance(note_widget, KanbanNote)
                            and note_widget.label.get_text() == note_text
                        ):
                            row.destroy()
                            break

                    # Add to Done column
                    done_column = self.columns[2]
                    done_column.add_note(note_text)

                    return True

        # Check if already in Done column
        done_notes = self.columns[2].get_notes()
        for note_text in done_notes:
            if search_text in note_text.lower():
                return False

        return False

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
        self._launcher_instance = None

    def initialize(self):
        """Initialize the Kanban plugin."""
        self.set_triggers(["kanban"])
        self.description = "Kanban board for task management. Use 'kanban add <text>' to add tasks, 'kanban move <text>' to move to next state. Keyboard: Enter/F2 to edit, Del to delete, Ctrl+N to add new note"
        self._setup_launcher_hooks()

    def cleanup(self):
        """Cleanup the Kanban plugin."""
        if self._current_widget:
            # Properly destroy the current widget
            if self._current_widget.get_parent():
                self._current_widget.get_parent().remove(self._current_widget)
            self._current_widget.destroy()
            self._current_widget = None
        self._pending_add_text = None
        self._cleanup_launcher_hooks()

    def _setup_launcher_hooks(self):
        """Setup hooks to monitor launcher state."""
        try:
            # Try to find the launcher instance using garbage collection (like bookmarks plugin)
            import gc

            for obj in gc.get_objects():
                if (
                    hasattr(obj, "__class__")
                    and obj.__class__.__name__ == "Launcher"
                    and hasattr(obj, "close_launcher")
                ):
                    self._launcher_instance = obj
                    break
        except Exception as e:
            print(f"Warning: Could not setup launcher hooks: {e}")

    def _cleanup_launcher_hooks(self):
        """Cleanup launcher hooks."""
        try:
            self._launcher_instance = None
        except Exception as e:
            print(f"Warning: Could not cleanup launcher hooks: {e}")

    def _reset_to_trigger(self):
        """Reset launcher to trigger word and refresh."""
        try:
            if self._launcher_instance and hasattr(
                self._launcher_instance, "search_entry"
            ):
                # Get the current trigger
                trigger = "kanban "

                # Reset to trigger word with space
                try:

                    def reset_and_refresh():
                        # Set text to trigger word
                        self._launcher_instance.search_entry.set_text(trigger)
                        # Position cursor at end
                        self._launcher_instance.search_entry.set_position(-1)
                        # Trigger search to show default kanban view
                        self._launcher_instance._perform_search(trigger)
                        return False

                    GLib.timeout_add(50, reset_and_refresh)
                except ImportError:
                    # Fallback: direct call if GLib not available
                    self._launcher_instance.search_entry.set_text(trigger)
                    self._launcher_instance.search_entry.set_position(-1)
                    self._launcher_instance._perform_search(trigger)
        except Exception as e:
            print(f"Could not reset to trigger: {e}")

    def _delayed_reset_for_add(self):
        """Reset to trigger with minimal delay for add operations."""
        try:
            GLib.timeout_add(50, lambda: (self._reset_to_trigger(), False))
        except ImportError:
            self._reset_to_trigger()

    def _find_todo_in_columns(self, search_text: str):
        """Find a todo by partial text match across all columns."""
        search_text = search_text.lower().strip()

        # Load current state to get fresh data
        if self._current_widget:
            for col_idx, column in enumerate(self._current_widget.columns):
                notes = column.get_notes()
                for note_text in notes:
                    if search_text in note_text.lower():
                        return col_idx, note_text
        return None, None

    def _move_todo_to_next_state(self, todo_text: str):
        """Move a todo to the next state (To Do -> In Progress -> Done)."""
        if not self._current_widget:
            return False, "Kanban board not initialized"

        col_idx, found_text = self._find_todo_in_columns(todo_text)
        if col_idx is None:
            return False, f"Todo '{todo_text}' not found"

        # Determine next column
        if col_idx == 0:  # To Do -> In Progress
            next_col_idx = 1
            next_state = "In Progress"
        elif col_idx == 1:  # In Progress -> Done
            next_col_idx = 2
            next_state = "Done"
        else:  # Already in Done
            return False, f"Todo '{found_text}' is already completed"

        # Remove from current column
        current_column = self._current_widget.columns[col_idx]
        for row in current_column.listbox.get_children():
            note_widget = row.get_children()[0]
            if (
                isinstance(note_widget, KanbanNote)
                and note_widget.label.get_text() == found_text
            ):
                row.destroy()
                break

        # Add to next column
        next_column = self._current_widget.columns[next_col_idx]
        next_column.add_note(found_text)

        # Save state
        self._current_widget.save_state()

        return True, f"Moved '{found_text}' to {next_state}"

    def _execute_move_action(self, todo_text: str):
        """Execute the move action and reset to trigger."""

        try:
            GLib.timeout_add(50, lambda: (self._reset_to_trigger(), False))
        except ImportError:
            self._reset_to_trigger()

    def _execute_complete_action(self, todo_text: str):
        """Execute the complete action (move directly to Done) and reset to trigger."""
        if not self._current_widget:
            return

        col_idx, found_text = self._find_todo_in_columns(todo_text)
        if col_idx is None:
            return

        if col_idx == 2:  # Already in Done
            return

        # Remove from current column
        current_column = self._current_widget.columns[col_idx]
        for row in current_column.listbox.get_children():
            note_widget = row.get_children()[0]
            if (
                isinstance(note_widget, KanbanNote)
                and note_widget.label.get_text() == found_text
            ):
                row.destroy()
                break

        # Add to Done column
        done_column = self._current_widget.columns[2]
        done_column.add_note(found_text)

        # Save state
        self._current_widget.save_state()

        # Reset to trigger word with minimal delay (like bookmarks plugin)
        try:
            GLib.timeout_add(50, lambda: (self._reset_to_trigger(), False))
        except ImportError:
            self._reset_to_trigger()

    def _execute_add_action(self, todo_text: str):
        """Execute the add action and reset to trigger."""
        if not self._current_widget:
            return

        # Add to To Do column
        self._current_widget.columns[0].add_note(todo_text)
        self._current_widget.save_state()

        # Reset to trigger word with minimal delay
        try:
            GLib.timeout_add(50, lambda: (self._reset_to_trigger(), False))
        except ImportError:
            self._reset_to_trigger()

    def query(self, query_string: str) -> List[Result]:
        """Process Kanban queries."""
        results = []
        query = query_string.strip()

        # Only create a new widget if we don't have one
        if not self._current_widget:
            kanban_widget = Kanban()
            kanban_widget.connect("todo-added", lambda _: self._delayed_reset_for_add())
            self._current_widget = kanban_widget
        else:
            kanban_widget = self._current_widget

        # Store pending command for Enter key handling (no preview results)
        if query.startswith("add "):
            note_text = query[4:].strip()
            if note_text:
                kanban_widget.set_pending_add_text(note_text)
                kanban_widget.pending_command = ("add", note_text)
            else:
                kanban_widget.set_pending_add_text(None)
                kanban_widget.pending_command = None
        elif query.startswith(("move ", "progress ")):
            command_parts = query.split(" ", 1)
            if len(command_parts) > 1:
                todo_text = command_parts[1].strip()
                if todo_text:
                    kanban_widget.pending_command = ("move", todo_text)
                else:
                    kanban_widget.pending_command = None
            else:
                kanban_widget.pending_command = None
        elif query.startswith(("done ", "complete ")):
            command_parts = query.split(" ", 1)
            if len(command_parts) > 1:
                todo_text = command_parts[1].strip()
                if todo_text:
                    kanban_widget.pending_command = ("done", todo_text)
                else:
                    kanban_widget.pending_command = None
            else:
                kanban_widget.pending_command = None
        else:
            kanban_widget.set_pending_add_text(None)
            kanban_widget.pending_command = None

        # Always show the kanban board widget
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
