"""
Kanban Plugin for Modus Launcher

A maintainable kanban board implementation with the following features:
- Three columns: To Do, In Progress, Done
- Drag and drop between columns
- Inline editing of notes
- Keyboard navigation and shortcuts
- Persistent state storage
- Command-based interaction (add, move, done)

Architecture:
- KanbanEditor: Handles inline text editing
- KanbanNote: Individual note widget with editing and drag/drop
- KanbanColumn: Column container with notes and drag/drop handling
- KanbanBoard: Main board widget with keyboard handling and state management
- KanbanPlugin: Plugin interface and command processing
"""

import json
import os
from pathlib import Path
from typing import List, Optional, Tuple

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

# Constants
KANBAN_STATE_FILE = Path(os.path.expanduser("~/.kanban.json"))
BOARD_HEIGHT = 500
COLUMN_HEIGHT = 150
EDITOR_MIN_HEIGHT = 50


def create_drag_surface(widget: Gtk.Widget) -> cairo.ImageSurface:
    """Create a cairo surface from a widget for drag operations."""
    alloc = widget.get_allocation()
    surface = cairo.ImageSurface(cairo.Format.ARGB32, alloc.width, alloc.height)
    cr = cairo.Context(surface)
    cr.set_source_rgba(0, 0, 0, 0)
    cr.rectangle(0, 0, alloc.width, alloc.height)
    cr.fill()
    widget.draw(cr)
    return surface


class KanbanEditor(Gtk.Box):
    """Inline text editor for kanban notes with confirm/cancel functionality."""

    __gsignals__ = {
        "confirmed": (GObject.SignalFlags.RUN_LAST, None, (str,)),
        "canceled": (GObject.SignalFlags.RUN_LAST, None, ()),
    }

    def __init__(self, initial_text=""):
        super().__init__(name="inline-editor", spacing=4)
        self._setup_text_view(initial_text)
        self._setup_buttons()
        self._setup_layout()
        self.show_all()

    def _setup_text_view(self, initial_text: str):
        """Setup the text view component."""
        self.text_view = Gtk.TextView()
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.text_view.connect("key-press-event", self._on_key_press)

        buffer = self.text_view.get_buffer()
        buffer.set_text(initial_text)

    def _setup_buttons(self):
        """Setup confirm and cancel buttons."""
        # Confirm button
        confirm_label = Label(name="kanban-btn-label", markup=icons.accept)
        self.confirm_btn = Gtk.Button(name="kanban-btn")
        self.confirm_btn.add(confirm_label)
        self.confirm_btn.connect("clicked", self._on_confirm_clicked)
        self.confirm_btn.get_style_context().add_class("flat")

        # Cancel button
        cancel_label = Label(name="kanban-btn-neg", markup=icons.cancel)
        self.cancel_btn = Gtk.Button(name="kanban-btn")
        self.cancel_btn.add(cancel_label)
        self.cancel_btn.connect("clicked", self._on_cancel_clicked)
        self.cancel_btn.get_style_context().add_class("flat")

    def _setup_layout(self):
        """Setup the widget layout."""
        # Scrolled window for text view
        scrolled_window = Gtk.ScrolledWindow(name="scrolled-window")
        scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.set_min_content_height(EDITOR_MIN_HEIGHT)
        scrolled_window.add(self.text_view)

        # Button container
        button_box = Gtk.Box(spacing=4)
        button_box.pack_start(self.confirm_btn, False, False, 0)
        button_box.pack_start(self.cancel_btn, False, False, 0)

        # Center the buttons
        center_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        center_box.set_halign(Gtk.Align.CENTER)
        center_box.pack_start(button_box, False, False, 0)

        # Main layout
        self.pack_start(scrolled_window, True, True, 0)
        self.pack_start(center_box, False, False, 0)

    def _get_text(self) -> str:
        """Get the current text from the editor."""
        buffer = self.text_view.get_buffer()
        start, end = buffer.get_bounds()
        return buffer.get_text(start, end, True).strip()

    def _on_confirm_clicked(self, _widget):
        """Handle confirm button click."""
        text = self._get_text()
        if text:
            self.emit("confirmed", text)
        else:
            self.emit("canceled")

    def _on_cancel_clicked(self, _widget):
        """Handle cancel button click."""
        self.emit("canceled")

    def _on_key_press(self, _widget, event):
        """Handle keyboard events."""
        if event.keyval == Gdk.KEY_Escape:
            self.emit("canceled")
            return True

        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if event.get_state() & Gdk.ModifierType.SHIFT_MASK:
                # Shift+Enter: Insert newline
                buffer = self.text_view.get_buffer()
                cursor_iter = buffer.get_iter_at_mark(buffer.get_insert())
                buffer.insert(cursor_iter, "\n")
                return True
            else:
                # Enter: Confirm
                self._on_confirm_clicked(None)
                return True
        return False


class KanbanNote(Gtk.EventBox):
    """Individual kanban note widget with editing, deletion, and drag/drop support."""

    __gsignals__ = {
        "changed": (GObject.SignalFlags.RUN_LAST, None, ()),
    }

    def __init__(self, text: str):
        super().__init__()
        self.text = text
        self.set_can_focus(True)  # Enable keyboard events

        self._setup_ui()
        self._setup_drag_and_drop()
        self._connect_signals()
        self.show_all()

    def _setup_ui(self):
        """Setup the note's user interface."""
        self.box = Gtk.Box(name="kanban-note", spacing=4)

        # Text label
        self.label = Gtk.Label(label=self.text)
        self.label.set_line_wrap(True)
        self.label.set_line_wrap_mode(Gtk.WrapMode.WORD)

        # Delete button
        delete_label = Label(name="kanban-btn-neg", markup=icons.trash)
        self.delete_btn = Gtk.Button(name="kanban-btn", child=delete_label)
        self.delete_btn.connect("clicked", self._on_delete_clicked)

        # Layout
        button_container = CenterBox(orientation="v", start_children=[self.delete_btn])
        self.box.pack_start(self.label, True, True, 0)
        self.box.pack_start(button_container, False, False, 0)
        self.add(self.box)

    def _setup_drag_and_drop(self):
        """Setup drag and drop functionality."""
        self.drag_source_set(
            Gdk.ModifierType.BUTTON1_MASK,
            [Gtk.TargetEntry.new("UTF8_STRING", Gtk.TargetFlags.SAME_APP, 0)],
            Gdk.DragAction.MOVE,
        )

    def _connect_signals(self):
        """Connect all signal handlers."""
        self.connect("button-press-event", self._on_button_press)
        self.connect("key-press-event", self._on_key_press)
        self.connect("drag-data-get", self._on_drag_data_get)
        self.connect("drag-data-delete", self._on_drag_data_delete)
        self.connect("drag-begin", self._on_drag_begin)

    def _on_button_press(self, _widget, event):
        """Handle mouse button press events."""
        if event.type == Gdk.EventType._2BUTTON_PRESS:
            self.start_edit()
            return False
        return True

    def _on_key_press(self, _widget, event):
        """Handle keyboard events for kanban notes."""
        keyval = event.keyval

        # Enter or F2 - start editing
        if keyval in (Gdk.KEY_Return, Gdk.KEY_F2):
            self.start_edit()
            return True

        # Delete - remove note
        if keyval == Gdk.KEY_Delete:
            self._delete_note()
            return True

        return False

    def _on_drag_begin(self, _widget, context):
        """Handle drag begin event."""
        surface = create_drag_surface(self)
        Gtk.drag_set_icon_surface(context, surface)

    def _on_drag_data_get(self, _widget, _drag_context, data, _info, _time):
        """Provide data for drag operation."""
        data.set_text(self.label.get_text(), -1)

    def _on_drag_data_delete(self, _widget, _drag_context):
        """Handle drag data deletion."""
        self._delete_note()

    def _on_delete_clicked(self, _button):
        """Handle delete button click."""
        self._delete_note()

    def _delete_note(self):
        """Delete this note from its parent."""
        parent = self.get_parent()
        if parent:
            parent.destroy()

    def start_edit(self):
        """Start inline editing of this note."""
        row = self.get_parent()
        if not row:
            return

        editor = KanbanEditor(self.label.get_text())
        editor.connect("confirmed", self._on_edit_confirmed)
        editor.connect("canceled", self._on_edit_canceled)

        # Replace self with editor
        row.remove(self)
        row.add(editor)
        row.show_all()

        # Focus the editor after a short delay
        GLib.timeout_add(50, lambda: (editor.text_view.grab_focus(), False))

    def _on_edit_confirmed(self, editor, text):
        """Handle edit confirmation."""
        self.label.set_text(text)
        self._replace_editor_with_self(editor)
        self.emit("changed")

    def _on_edit_canceled(self, editor):
        """Handle edit cancellation."""
        self._replace_editor_with_self(editor)

    def _replace_editor_with_self(self, editor):
        """Replace the editor with this note widget."""
        row = editor.get_parent()
        if row:
            row.remove(editor)
            row.add(self)
            row.show_all()


class KanbanColumn(Gtk.Frame):
    """A kanban column containing notes with drag/drop support."""

    __gsignals__ = {
        "changed": (GObject.SignalFlags.RUN_LAST, None, ()),
    }

    def __init__(self, title: str):
        super().__init__(name="kanban-column")
        self.title = title
        self._setup_ui()
        self._setup_drag_and_drop()
        self._configure_size()
        self.show_all()

    def _configure_size(self):
        """Configure size constraints for launcher compatibility."""
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_size_request(-1, COLUMN_HEIGHT)

    def _setup_ui(self):
        """Setup the column's user interface."""
        # Main container
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        # Notes list
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)

        # Add button
        add_label = Label(name="kanban-btn-label", markup=icons.add)
        self.add_btn = Gtk.Button(name="kanban-btn-add", child=add_label)
        self.add_btn.connect("clicked", self._on_add_clicked)

        # Header with title and add button
        title_label = Label(name="column-header", label=self.title)
        header = CenterBox(
            name="kanban-header",
            center_children=[title_label],
            end_children=[self.add_btn],
        )

        # Scrolled window for notes
        self.scroller = ScrolledWindow(
            name="scrolled-window",
            propagate_height=False,
            propagate_width=False
        )
        self.scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroller.add(self.listbox)
        self.scroller.set_vexpand(True)

        # Layout
        self.box.pack_start(header, False, False, 0)
        self.box.pack_start(self.scroller, True, True, 0)
        self.box.pack_start(self.add_btn, False, False, 0)
        self.add(self.box)

    def _setup_drag_and_drop(self):
        """Setup drag and drop functionality."""
        self.listbox.drag_dest_set(
            Gtk.DestDefaults.ALL,
            [Gtk.TargetEntry.new("UTF8_STRING", Gtk.TargetFlags.SAME_APP, 0)],
            Gdk.DragAction.MOVE,
        )

        # Connect drag and drop signals
        self.listbox.connect("drag-data-received", self._on_drag_data_received)
        self.listbox.connect("drag-motion", self._on_drag_motion)
        self.listbox.connect("drag-leave", self._on_drag_leave)

    def _on_add_clicked(self, _button):
        """Handle add button click to create a new note."""
        editor = KanbanEditor()
        row = Gtk.ListBoxRow(name="kanban-row")
        row.add(editor)
        self.listbox.add(row)
        self.listbox.show_all()
        editor.text_view.grab_focus()

        # Connect editor signals
        editor.connect("confirmed", self._on_editor_confirmed)
        editor.connect("canceled", self._on_editor_canceled)

        # Scroll to bottom after row is loaded
        GLib.idle_add(self._scroll_to_bottom)

    def _on_editor_confirmed(self, editor, text):
        """Handle editor confirmation for new note."""
        note = KanbanNote(text)
        note.connect("changed", lambda _: self.emit("changed"))

        # Replace editor with note
        row = editor.get_parent()
        if row:
            row.remove(editor)
            row.add(note)
            self.listbox.show_all()
            self.emit("changed")

    def _on_editor_canceled(self, editor):
        """Handle editor cancellation for new note."""
        row = editor.get_parent()
        if row:
            row.destroy()

    def _scroll_to_bottom(self):
        """Scroll the column to the bottom."""
        adj = self.scroller.get_vadjustment()
        adj.set_value(adj.get_upper())
        return False  # Don't repeat

    def add_note(self, text: str, suppress_signal: bool = False):
        """Add a new note to this column."""
        note = KanbanNote(text)
        note.connect("changed", lambda _: self.emit("changed"))

        row = Gtk.ListBoxRow(name="kanban-row")
        row.add(note)
        row.connect("destroy", lambda _: self.emit("changed"))

        self.listbox.add(row)
        self.listbox.show_all()

        if not suppress_signal:
            self.emit("changed")

    def get_notes(self) -> List[str]:
        """Get all note texts in this column."""
        return [
            row.get_children()[0].label.get_text()
            for row in self.listbox.get_children()
            if row.get_children() and isinstance(row.get_children()[0], KanbanNote)
        ]

    def clear_notes(self, suppress_signal: bool = False):
        """Clear all notes from this column."""
        for row in self.listbox.get_children():
            row.destroy()
        if not suppress_signal:
            self.emit("changed")

    def _on_drag_data_received(self, _widget, drag_context, _x, y, data, _info, time):
        """Handle drag data received event."""
        text = data.get_text()
        if not text:
            return

        # Find insertion point
        row = self.listbox.get_row_at_y(y)

        # Create new note
        new_note = KanbanNote(text)
        new_note.connect("changed", lambda _: self.emit("changed"))
        new_row = Gtk.ListBoxRow(name="kanban-row")
        new_row.add(new_note)
        new_row.connect("destroy", lambda _: self.emit("changed"))

        # Insert at appropriate position
        if row:
            self.listbox.insert(new_row, row.get_index())
        else:
            self.listbox.add(new_row)

        self.listbox.show_all()
        drag_context.finish(True, False, time)
        self.emit("changed")

    def _on_drag_motion(self, _widget, drag_context, _x, _y, time):
        """Handle drag motion event."""
        Gdk.drag_status(drag_context, Gdk.DragAction.MOVE, time)
        return True

    def _on_drag_leave(self, widget, _drag_context, _time):
        """Handle drag leave event."""
        widget.get_parent().get_parent().drag_unhighlight()


class KanbanBoard(Gtk.Box):
    """Main kanban board widget with three columns and command handling."""

    __gsignals__ = {
        "todo-added": (GObject.SignalFlags.RUN_LAST, None, ()),
    }

    def __init__(self):
        super().__init__(name="kanban", orientation=Gtk.Orientation.VERTICAL)

        # Command state
        self.pending_add_text = None
        self.pending_command = None

        self._setup_ui()
        self._setup_columns()
        self._load_state()
        self.show_all()

    def _setup_ui(self):
        """Setup the board's user interface."""
        # Configure size for launcher compatibility
        self.set_size_request(-1, BOARD_HEIGHT)
        self.set_vexpand(False)
        self.set_hexpand(True)
        self.set_can_focus(True)

        # Connect keyboard events
        self.connect("key-press-event", self._on_key_press)

        # Hidden entry for launcher Enter key handling
        from fabric.widgets.entry import Entry
        self.hidden_entry = Entry(name="kanban-hidden-entry")
        self.hidden_entry.set_size_request(1, 1)
        self.hidden_entry.set_opacity(0.0)
        self.hidden_entry.connect("activate", self._on_hidden_entry_activate)
        self.add(self.hidden_entry)

        # Grid for columns
        self.grid = Gtk.Grid(
            column_spacing=4,
            column_homogeneous=True,
            row_spacing=4,
            row_homogeneous=True,
        )
        self.grid.set_vexpand(True)
        self.grid.set_hexpand(True)
        self.add(self.grid)

    def _setup_columns(self):
        """Setup the kanban columns."""
        self.columns = [
            KanbanColumn("To Do"),
            KanbanColumn("In Progress"),
            KanbanColumn("Done"),
        ]

        # Arrange columns vertically (stacked)
        for i, column in enumerate(self.columns):
            self.grid.attach(column, 0, i, 1, 1)
            column.connect("changed", lambda _: self._save_state())

    def _load_state(self):
        """Load kanban state from file."""
        try:
            with open(KANBAN_STATE_FILE, "r") as f:
                state = json.load(f)
                for col_data in state["columns"]:
                    for column in self.columns:
                        if column.title == col_data["title"]:
                            column.clear_notes(suppress_signal=True)
                            for note_text in col_data["notes"]:
                                column.add_note(note_text, suppress_signal=True)
                            break
        except FileNotFoundError:
            pass  # No state file yet
        except Exception as e:
            print(f"Error loading kanban state: {e}")

    def _save_state(self):
        """Save kanban state to file."""
        state = {
            "columns": [
                {"title": col.title, "notes": col.get_notes()}
                for col in self.columns
            ]
        }
        try:
            with open(KANBAN_STATE_FILE, "w") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f"Error saving kanban state: {e}")

    def _on_key_press(self, _widget, event):
        """Handle key press events for the kanban widget."""
        keyval = event.keyval

        # Enter - handle pending commands
        if keyval == Gdk.KEY_Return:
            return self._handle_enter_key()

        # Ctrl+N - add new note to first column
        if keyval == Gdk.KEY_n and event.state & Gdk.ModifierType.CONTROL_MASK:
            self.columns[0]._on_add_clicked(None)
            return True

        # Ctrl+1, Ctrl+2, Ctrl+3 - add note to specific column
        if event.state & Gdk.ModifierType.CONTROL_MASK:
            column_shortcuts = {
                Gdk.KEY_1: 0,
                Gdk.KEY_2: 1,
                Gdk.KEY_3: 2
            }
            if keyval in column_shortcuts:
                column_idx = column_shortcuts[keyval]
                if column_idx < len(self.columns):
                    self.columns[column_idx]._on_add_clicked(None)
                    return True

        return False

    def _handle_enter_key(self) -> bool:
        """Handle Enter key press for command execution."""
        if self.pending_command:
            command, text = self.pending_command
            success = False

            if command == "add":
                self.columns[0].add_note(text)
                success = True
            elif command == "move":
                success = self._execute_move_command(text)
            elif command == "done":
                success = self._execute_done_command(text)

            if success:
                self._save_state()

            # Clear pending command and notify plugin to reset
            self._clear_pending_commands()
            self.emit("todo-added")  # Signal for plugin reset
            return True

        elif self.pending_add_text:
            # Fallback for old add system
            self.columns[0].add_note(self.pending_add_text)
            self._save_state()
            self._clear_pending_commands()
            self.emit("todo-added")
            return True

        return False

    def _on_hidden_entry_activate(self, _entry):
        """Handle activation of the hidden entry (Enter key from launcher)."""
        self._handle_enter_key()

    def _clear_pending_commands(self):
        """Clear all pending command state."""
        self.pending_command = None
        self.pending_add_text = None

    def set_pending_add_text(self, text: str):
        """Set the pending add text for Enter key handling."""
        self.pending_add_text = text

    def _execute_move_command(self, todo_text: str) -> bool:
        """Execute move command to advance todo to next state."""
        search_text = todo_text.lower().strip()

        # Find todo across all columns
        for col_idx, column in enumerate(self.columns):
            notes = column.get_notes()
            for note_text in notes:
                if search_text in note_text.lower():
                    return self._move_note_to_next_column(column, note_text, col_idx)
        return False

    def _execute_done_command(self, todo_text: str) -> bool:
        """Execute done command to move todo directly to Done column."""
        search_text = todo_text.lower().strip()

        # Find todo in To Do and In Progress columns only
        for column in self.columns[:2]:
            notes = column.get_notes()
            for note_text in notes:
                if search_text in note_text.lower():
                    return self._move_note_to_done_column(column, note_text)

        # Check if already in Done column
        done_notes = self.columns[2].get_notes()
        return not any(search_text in note.lower() for note in done_notes)

    def _move_note_to_next_column(self, current_column: KanbanColumn, note_text: str, col_idx: int) -> bool:
        """Move a note to the next column in sequence."""
        # Determine next column
        if col_idx == 0:  # To Do -> In Progress
            next_col_idx = 1
        elif col_idx == 1:  # In Progress -> Done
            next_col_idx = 2
        else:  # Already in Done
            return False

        # Remove from current column and add to next
        self._remove_note_from_column(current_column, note_text)
        self.columns[next_col_idx].add_note(note_text)
        return True

    def _move_note_to_done_column(self, current_column: KanbanColumn, note_text: str) -> bool:
        """Move a note directly to the Done column."""
        self._remove_note_from_column(current_column, note_text)
        self.columns[2].add_note(note_text)  # Done column
        return True

    def _remove_note_from_column(self, column: KanbanColumn, note_text: str):
        """Remove a specific note from a column."""
        for row in column.listbox.get_children():
            if row.get_children():
                note_widget = row.get_children()[0]
                if (isinstance(note_widget, KanbanNote) and
                    note_widget.label.get_text() == note_text):
                    row.destroy()
                    break


class KanbanPlugin(PluginBase):
    """Kanban board plugin for the launcher providing task management interface."""

    def __init__(self):
        super().__init__()
        self.display_name = "Kanban"
        self.description = "Kanban board for task management"
        self._current_widget = None
        self._launcher_instance = None

    def initialize(self):
        """Initialize the Kanban plugin."""
        self.set_triggers(["kanban"])
        self.description = (
            "Kanban board for task management. "
            "Commands: 'add <text>', 'move <text>', 'done <text>'. "
            "Keyboard: Enter/F2 to edit, Del to delete, Ctrl+N to add note"
        )
        self._setup_launcher_hooks()

    def cleanup(self):
        """Cleanup the Kanban plugin."""
        if self._current_widget:
            self._destroy_current_widget()
        self._cleanup_launcher_hooks()

    def _destroy_current_widget(self):
        """Safely destroy the current widget."""
        if self._current_widget.get_parent():
            self._current_widget.get_parent().remove(self._current_widget)
        self._current_widget.destroy()
        self._current_widget = None

    def _setup_launcher_hooks(self):
        """Setup hooks to monitor launcher state."""
        try:
            import gc
            # Find the launcher instance using garbage collection
            for obj in gc.get_objects():
                if (hasattr(obj, "__class__") and
                    obj.__class__.__name__ == "Launcher" and
                    hasattr(obj, "close_launcher")):
                    self._launcher_instance = obj
                    break
        except Exception as e:
            print(f"Warning: Could not setup launcher hooks: {e}")

    def _cleanup_launcher_hooks(self):
        """Cleanup launcher hooks."""
        self._launcher_instance = None

    def _reset_to_trigger(self):
        """Reset launcher to trigger word and refresh."""
        if not (self._launcher_instance and
                hasattr(self._launcher_instance, "search_entry")):
            return

        trigger = "kanban "
        try:
            def reset_and_refresh():
                self._launcher_instance.search_entry.set_text(trigger)
                self._launcher_instance.search_entry.set_position(-1)
                self._launcher_instance._perform_search(trigger)
                return False

            GLib.timeout_add(50, reset_and_refresh)
        except Exception as e:
            print(f"Could not reset to trigger: {e}")

    def _delayed_reset_for_add(self):
        """Reset to trigger with minimal delay for add operations."""
        try:
            GLib.timeout_add(50, lambda: (self._reset_to_trigger(), False))
        except ImportError:
            self._reset_to_trigger()

    def _find_todo_in_columns(self, search_text: str) -> Tuple[Optional[int], Optional[str]]:
        """Find a todo by partial text match across all columns."""
        if not self._current_widget:
            return None, None

        search_text = search_text.lower().strip()
        for col_idx, column in enumerate(self._current_widget.columns):
            notes = column.get_notes()
            for note_text in notes:
                if search_text in note_text.lower():
                    return col_idx, note_text
        return None, None

    def _move_todo_to_next_state(self, todo_text: str) -> Tuple[bool, str]:
        """Move a todo to the next state (To Do -> In Progress -> Done)."""
        if not self._current_widget:
            return False, "Kanban board not initialized"

        col_idx, found_text = self._find_todo_in_columns(todo_text)
        if col_idx is None:
            return False, f"Todo '{todo_text}' not found"

        # Determine next column
        state_transitions = {
            0: (1, "In Progress"),  # To Do -> In Progress
            1: (2, "Done"),         # In Progress -> Done
        }

        if col_idx not in state_transitions:
            return False, f"Todo '{found_text}' is already completed"

        next_col_idx, next_state = state_transitions[col_idx]

        # Move the note
        self._current_widget._remove_note_from_column(
            self._current_widget.columns[col_idx], found_text
        )
        self._current_widget.columns[next_col_idx].add_note(found_text)
        self._current_widget._save_state()

        return True, f"Moved '{found_text}' to {next_state}"

    def _execute_complete_action(self, todo_text: str):
        """Execute the complete action (move directly to Done) and reset to trigger."""
        if not self._current_widget:
            return

        col_idx, found_text = self._find_todo_in_columns(todo_text)
        if col_idx is None or col_idx == 2:  # Not found or already in Done
            return

        # Move to Done column
        self._current_widget._remove_note_from_column(
            self._current_widget.columns[col_idx], found_text
        )
        self._current_widget.columns[2].add_note(found_text)
        self._current_widget._save_state()
        self._delayed_reset_for_add()

    def _execute_add_action(self, todo_text: str):
        """Execute the add action and reset to trigger."""
        if not self._current_widget:
            return

        self._current_widget.columns[0].add_note(todo_text)
        self._current_widget._save_state()
        self._delayed_reset_for_add()

    def query(self, query_string: str) -> List[Result]:
        """Process Kanban queries and return results."""
        query = query_string.strip()

        # Get or create kanban widget
        kanban_widget = self._get_or_create_widget()

        # Process command and set pending state
        self._process_command(kanban_widget, query)

        # Return kanban board result
        return [self._create_kanban_result(kanban_widget)]

    def _get_or_create_widget(self) -> KanbanBoard:
        """Get existing widget or create a new one."""
        if not self._current_widget:
            self._current_widget = KanbanBoard()
            self._current_widget.connect("todo-added", lambda _: self._delayed_reset_for_add())
        return self._current_widget

    def _process_command(self, widget: KanbanBoard, query: str):
        """Process the query command and set pending state."""
        # Clear previous state
        widget.set_pending_add_text(None)
        widget.pending_command = None

        # Parse commands
        if query.startswith("add "):
            note_text = query[4:].strip()
            if note_text:
                widget.set_pending_add_text(note_text)
                widget.pending_command = ("add", note_text)

        elif query.startswith(("move ", "progress ")):
            todo_text = self._extract_command_text(query)
            if todo_text:
                widget.pending_command = ("move", todo_text)

        elif query.startswith(("done ", "complete ")):
            todo_text = self._extract_command_text(query)
            if todo_text:
                widget.pending_command = ("done", todo_text)

    def _extract_command_text(self, query: str) -> Optional[str]:
        """Extract text from command query."""
        parts = query.split(" ", 1)
        return parts[1].strip() if len(parts) > 1 else None

    def _create_kanban_result(self, widget: KanbanBoard) -> Result:
        """Create the kanban board result."""
        return Result(
            title="Kanban Board",
            subtitle="Task management with kanban-style columns",
            icon_markup=icons.kanban,
            action=lambda: None,  # Widget handles Enter key
            relevance=1.0,
            plugin_name=self.display_name,
            custom_widget=widget,
            data={"type": "kanban_board", "keep_launcher_open": True},
        )
