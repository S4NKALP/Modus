from collections.abc import Iterator

from fabric.utils import Gdk, exec_shell_command_async, idle_add, remove_handler
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.label import Label

from modules.launcher.base import LauncherPlugin
from services import TmuxService
from utils.functions import terminal_exec_command


class TmuxPlugin(LauncherPlugin):
    @property
    def name(self) -> str:
        return "tmux"

    @property
    def icon(self) -> str:
        return "terminal-symbolic"

    @property
    def keywords(self) -> list[str]:
        return ["tmux"]

    def __init__(self, handler):
        super().__init__(handler)
        self._query_handler: int = 0
        self.current_slots: list = []
        self.tmux_service = TmuxService()
        self.sessions: list = []
        self.terminal = "kitty"

    def on_search(self, text: str) -> None:
        self.query_tmux(text)

    def stop(self):
        if self._query_handler:
            remove_handler(self._query_handler)
            self._query_handler = 0
        self.current_slots.clear()

    def query_tmux(self, text: str) -> None:
        self.handler.start("tmux")
        self.current_slots.clear()
        text_stripped = text.strip()

        commands = {
            "new": self._handle_new_command,
            "kill": self._handle_kill_command,
            "rename": self._handle_rename_command,
            "terminal": self._handle_terminal_command,
            "help": lambda t: self._show_command_help(),
        }

        for prefix, handler in commands.items():
            if text_stripped.startswith(prefix):
                handler(text)
                return

        self._load_and_display_sessions(text)

    def _load_and_display_sessions(self, text: str) -> None:
        result = self.tmux_service.list_sessions()
        if not result["success"]:
            self._show_error_message(f"Failed to load sessions: {result['error']}")
            return

        self.sessions = result["data"]

        if not self.sessions:
            self._show_no_sessions()
            return

        filtered_sessions = self._filter_sessions(text)
        if not filtered_sessions:
            self._show_no_results()
            return

        self._query_handler = idle_add(
            self._bake_next_session_slot, iter(filtered_sessions), pin=True
        )

    def _filter_sessions(self, text: str) -> Iterator[dict]:
        if not text.strip():
            return iter(self.sessions)

        text_lower = text.lower()
        return iter(
            session
            for session in self.sessions
            if text_lower in session.get("name", "").lower()
        )

    def _show_no_sessions(self) -> None:
        self.handler.slot_ready(
            Button(
                style_classes="app-slot tmux-no-sessions",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Label(
                            label="No active tmux sessions",
                            style_classes="tmux-no-sessions-text",
                            h_align="center",
                        ),
                    ],
                ),
                tooltip_text="Use 'new session_name' to create a session",
            ),
            "tmux",
        )
        self.handler.done()

    def _show_no_results(self) -> None:
        self.handler.slot_ready(
            Button(
                style_classes="app-slot tmux-no-results",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Label(
                            label="No sessions match your search",
                            style_classes="tmux-no-results-text",
                            h_align="center",
                        ),
                    ],
                ),
            ),
            "tmux",
        )
        self.handler.done()

    def _bake_next_session_slot(self, iterator: Iterator[dict]) -> bool:
        try:
            session = next(iterator)
        except StopIteration:
            idle_add(self.handler.done)
            return False

        self._create_session_slot(session)
        return True

    def _create_session_slot(self, session: dict) -> None:
        session_name = session.get("name", "")
        windows = session.get("windows", 0)
        created = session.get("created", "")
        attached = session.get("attached", False)

        status_icon = "●" if attached else "○"
        status_color = "attached" if attached else "detached"

        name_label = Label(
            label=f"{status_icon} {session_name}",
            style_classes=f"tmux-session-name tmux-{status_color}",
            h_align="start",
            max_chars_width=25,
            ellipsization="end",
        )

        info_label = Label(
            label=f"{windows} windows • Created: {created}",
            style_classes="tmux-session-info",
            h_align="start",
            max_chars_width=40,
            ellipsization="end",
        )

        slot_widget = Button(
            style_classes=f"app-slot tmux-slot tmux-{status_color}",
            child=Box(
                orientation="v",
                spacing=4,
                children=[
                    name_label,
                    info_label,
                ],
            ),
            tooltip_text=f"Click to attach\nShift+Enter to kill session\nAlt+Enter to rename session\nAttached: {'Yes' if attached else 'No'}",
            on_clicked=lambda *_: self._attach_session(session_name),
        )

        slot_widget.connect(
            "key-press-event",
            lambda widget, event, s_name=session_name: self._on_slot_key_press(
                widget, event, s_name
            ),
        )

        slot_info = {
            "widget": slot_widget,
            "name_label": name_label,
            "info_label": info_label,
            "session_name": session_name,
            "session": session,
        }
        self.current_slots.append(slot_info)
        self.handler.slot_ready(slot_widget, "tmux")

    def _attach_session(self, session_name: str) -> None:
        cmd = f"tmux attach -t {session_name}"
        term_cmd = terminal_exec_command(self.terminal, cmd)
        exec_shell_command_async(term_cmd)
        self.handler.launched()

    def _kill_session(self, session_name: str) -> None:
        result = self.tmux_service.kill_session(session_name)
        if not result["success"]:
            self._show_error_message(f"Failed to kill session: {result['error']}")
            return

        self._refresh_session_list()

    def _on_slot_key_press(self, widget, event, session_name: str) -> bool:
        if not event:
            return False

        # Shift+Enter: Kill session
        if (
            event.keyval == Gdk.KEY_Return or event.keyval == Gdk.KEY_KP_Enter
        ) and event.state & Gdk.ModifierType.SHIFT_MASK:
            return self._kill_session(session_name) or True

        # Alt+Enter: Rename session (pre-fill input)
        if (
            event.keyval == Gdk.KEY_Return or event.keyval == Gdk.KEY_KP_Enter
        ) and event.state & Gdk.ModifierType.MOD1_MASK:
            # This would require updating the input field, which we can't easily do directly from here
            # without a callback or reference to the entry.
            # For now, we can just show a message or handle it if we add that capability.
            pass

        return False

    def _handle_new_command(self, text: str) -> None:
        if not text.strip().endswith(";"):
            self._show_error_message(
                "New session command must end with ';'\n\nUsage: new session_name;"
            )
            return

        command_text = text.strip()[:-1]
        parts = command_text.split()

        if len(parts) < 2:
            self._show_command_help("new")
            return

        session_name = parts[1]
        result = self.tmux_service.new_session(session_name)
        if not result["success"]:
            self._show_error_message(f"Error creating session: {result['error']}")
            return

        if hasattr(self.handler, "clear_input"):
            self.handler.clear_input()
        self._refresh_session_list()
        # Optionally attach immediately
        self._attach_session(session_name)

    def _handle_kill_command(self, text: str) -> None:
        if text.strip() == "kill":
            self._load_and_display_sessions("")
            return

        if not text.strip().endswith(";"):
            self._show_error_message(
                "Kill command must end with ';'\n\nUsage: kill session_name;"
            )
            return

        command_text = text.strip()[:-1]
        parts = command_text.split()

        if len(parts) < 2:
            self._show_command_help("kill")
            return

        session_name = parts[1]
        self._kill_session(session_name)

    def _handle_rename_command(self, text: str) -> None:
        if text.strip() == "rename":
            self._load_and_display_sessions("")
            return

        if not text.strip().endswith(";"):
            self._show_error_message(
                "Rename command must end with ';'\n\nUsage: rename old_name new_name;"
            )
            return

        command_text = text.strip()[:-1]
        parts = command_text.split()

        if len(parts) < 3:
            self._show_command_help("rename")
            return

        old_name = parts[1]
        new_name = parts[2]

        result = self.tmux_service.rename_session(old_name, new_name)
        if not result["success"]:
            self._show_error_message(f"Error renaming session: {result['error']}")
            return

        if hasattr(self.handler, "clear_input"):
            self.handler.clear_input()
        self._refresh_session_list()

    def _handle_terminal_command(self, text: str) -> None:
        parts = text.strip().split()
        if len(parts) < 2:
            self._show_command_help("terminal")
            return
        self.terminal = parts[1]
        self._refresh_session_list()

    def _show_command_help(self, command: str = None) -> None:
        help_texts = {
            "new": "Usage: new session_name;\nExample: new dev;",
            "kill": "Usage: kill session_name;\nExample: kill dev;",
            "rename": "Usage: rename old_name new_name;\nExample: rename dev work;",
            "terminal": "Usage: terminal terminal_name\nExample: terminal kitty",
        }

        help_text = help_texts.get(
            command,
            """Available commands:
• new session_name; - Create new session
• kill session_name; - Kill session
• rename old_name new_name; - Rename session
• terminal terminal_name - Set terminal emulator
• help - Show this help

Note: Commands with arguments must end with semicolon (;)
Click to attach, Shift+Enter to kill""",
        )

        self.handler.slot_ready(
            Button(
                style_classes="app-slot tmux-help",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Label(
                            label=help_text,
                            style_classes="tmux-help-text",
                            h_align="center",
                        ),
                    ],
                ),
            ),
            "tmux",
        )
        self.handler.done()

    def _show_error_message(self, message: str) -> None:
        self.handler.slot_ready(
            Button(
                style_classes="app-slot tmux-error",
                child=Box(
                    orientation="h",
                    spacing=12,
                    children=[
                        Label(
                            label=message,
                            style_classes="tmux-error-text",
                            h_align="center",
                        ),
                    ],
                ),
                on_clicked=lambda *_: self.handler.launched(),
            ),
            "tmux",
        )
        self.handler.done()

    def _refresh_session_list(self) -> None:
        self.current_slots.clear()
        if hasattr(self.handler, "clear_viewport"):
            self.handler.clear_viewport()
        idle_add(self._show_session_list)

    def _show_session_list(self) -> None:
        self.handler.start("tmux")
        self._load_and_display_sessions("")

    def handle_external(self, command: str, args: str) -> None:
        # Map external commands if needed
        pass
