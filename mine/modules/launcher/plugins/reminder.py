from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from fabric.utils import (
    Gdk,
    GLib,
    exec_shell_command_async,
    idle_add,
    re,
    remove_handler,
)
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.image import Image
from fabric.widgets.label import Label

import config.data as data
from modules.launcher.base import LauncherPlugin


@dataclass
class ReminderOption:
    name: str
    arg: str
    icon: str = "alarm-symbolic"


class ReminderPlugin(LauncherPlugin):
    @property
    def name(self) -> str:
        return "reminder"

    @property
    def icon(self) -> str:
        return "alarm-symbolic"

    @property
    def keywords(self) -> list[str]:
        return ["remind", "alarm"]

    def __init__(self, handler):
        super().__init__(handler)
        self._query_handler: int = 0
        self._active_timeouts: list[int] = []

        self.presets: list[ReminderOption] = [
            ReminderOption(name="In 5 minutes", arg="5m"),
            ReminderOption(name="In 10 minutes", arg="10m"),
            ReminderOption(name="In 30 minutes", arg="30m"),
            ReminderOption(name="In 1 hour", arg="1h"),
        ]

    def on_search(self, text: str) -> None:
        self.query_reminder(text)

    def stop(self):
        self._query_handler and remove_handler(self._query_handler)
        self._query_handler = 0

        for source_id in self._active_timeouts:
            GLib.source_remove(source_id)
        self._active_timeouts.clear()

    def handle_external(self, command: str, args: str) -> None:
        # This plugin can handle direct commands if needed, but for now we rely on query
        pass

    def handle_direct(self, text: str) -> bool:
        # This was in the original code, possibly used by main.py directly?
        # In the new architecture, we might want to expose this differently or just use on_search.
        # But if main.py calls this directly for "remind 5m", we can keep it or adapt.
        # For now, let's keep the logic available.
        q = text.strip()
        if not q:
            return False
        ms, body = self._parse_input_to_ms_and_body(q)
        if ms is None:
            self._notify("⏰ Reminder", f"Invalid time: {q}")
            return True
        self._schedule_ms(ms, body)
        return True

    def query_reminder(self, text: str) -> None:
        self.handler.start("reminder")

        text_stripped = text.strip()
        options = [o.__dict__ for o in self.presets]

        if text_stripped and text_stripped not in {o["arg"] for o in options}:
            options.insert(
                0,
                {
                    "name": f"Custom: {text_stripped}",
                    "arg": text_stripped,
                    "icon": "document-send-symbolic",
                },
            )

        filtered_options = self._filter_options(text, options)
        if not filtered_options:
            return

        self._query_handler = idle_add(
            self._bake_next_option_slot, iter(filtered_options), pin=True
        )

    def _filter_options(self, text: str, options: list[dict]) -> list[dict]:
        return (
            options
            if not text.strip()
            else [
                option
                for option in options
                if text.lower() in option["name"].lower()
                or text.lower() in option["arg"].lower()
            ]
        )

    def _bake_next_option_slot(self, iterator: Iterable[dict]) -> bool:
        option = next(iterator, None)
        if option is None:
            idle_add(self.handler.done)
            return False
        self._create_option_slot(option)
        return True

    def _create_option_slot(self, option: dict) -> None:
        slot_content = Box(
            orientation="h",
            spacing=12,
            children=[
                Image(icon_name=option["icon"], h_align="start", size=32),
                Box(
                    orientation="v",
                    children=[
                        Label(
                            label=f"Reminder: {option['name']}",
                            style_classes="reminder-name",
                            h_align="start",
                            v_align="start",
                        ),
                        Label(
                            label=f"Schedule reminder '{option['arg']}'",
                            style_classes="reminder-description",
                            h_align="start",
                            v_align="start",
                        ),
                    ],
                ),
            ],
        )

        slot_widget = Button(
            style_classes="app-slot reminder-slot",
            child=slot_content,
            tooltip_text=f"Click to schedule reminder: {option['arg']}",
            on_clicked=lambda *_: (
                self.handler.launched(),
                self._schedule_reminder(option["arg"], body=None),
            ),
        )

        slot_widget.connect(
            "key-press-event",
            lambda widget, event, opt=option: self._on_slot_key_press(
                widget, event, opt
            ),
        )

        self.handler.slot_ready(slot_widget, "reminder")

    def _on_slot_key_press(self, widget, event, option) -> bool:
        if not event or event.keyval not in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            return False
        self.handler.launched()
        self._schedule_reminder(option["arg"], body=None)
        return True

    def _schedule_reminder(self, arg: str, body: str | None) -> None:
        ms = self._parse_delay_to_ms(arg.lower().strip())
        if ms is None:
            self._notify("⏰ Reminder", f"Invalid time: {arg}")
            return
        self._schedule_ms(ms, body)

    def _schedule_ms(self, milliseconds: int, body: str | None) -> None:
        when = datetime.now() + timedelta(milliseconds=milliseconds)
        display_when = when.replace(second=0, microsecond=0)
        if when.second != 0 or when.microsecond != 0:
            display_when += timedelta(minutes=1)
        self._notify("⏰ Reminder", f"Scheduled for {display_when.strftime('%H:%M')}")

        def fire() -> bool:
            self._notify("⏰ Reminder", body or "Time's up!")
            return False

        source_id = GLib.timeout_add(milliseconds, fire)
        self._active_timeouts.append(source_id)

    def _parse_delay_to_ms(self, duration: str) -> int | None:
        if (
            len(duration) == 5
            and duration[2] == ":"
            and duration[:2].isdigit()
            and duration[3:].isdigit()
        ):
            hh = int(duration[:2])
            mm = int(duration[3:])
            now = datetime.now()
            fire_at = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if fire_at <= now:
                fire_at += timedelta(days=1)
            return int((fire_at - now).total_seconds() * 1000)

        norm = (
            duration.replace("minutes", "m")
            .replace("minute", "m")
            .replace("mins", "m")
            .replace("min", "m")
            .replace("hours", "h")
            .replace("hour", "h")
            .replace("hrs", "h")
            .replace("hr", "h")
            .replace("seconds", "s")
            .replace("second", "s")
            .replace("secs", "s")
            .replace("sec", "s")
            .replace("days", "d")
            .replace("day", "d")
        )
        norm = "".join(norm.split())  # remove spaces

        if norm.isdigit():
            return int(norm) * 60_000

        matches = list(re.finditer(r"(\d+)([smhd])", norm))
        if matches and matches[0].start() == 0:
            total_ms = 0
            for m in matches:
                val = int(m.group(1))
                unit = m.group(2)
                if unit == "s":
                    total_ms += val * 1000
                elif unit == "m":
                    total_ms += val * 60_000
                elif unit == "h":
                    total_ms += val * 60 * 60_000
                elif unit == "d":
                    total_ms += val * 24 * 60 * 60_000
            return total_ms if total_ms > 0 else None

        return None

    def _parse_input_to_ms_and_body(self, text: str) -> tuple[int | None, str | None]:
        lower = text.strip().lower()
        if lower.startswith("in "):
            lower = lower[3:].strip()

        m_abs = re.match(r"^(\d{1,2}:\d{2})(?:\s+(.+))?$", lower)
        if m_abs:
            ms = self._parse_delay_to_ms(m_abs.group(1))
            body = (m_abs.group(2) or "").strip() or None
            return ms, body

        norm = (
            lower.replace("minutes", "m")
            .replace("minute", "m")
            .replace("mins", "m")
            .replace("min", "m")
            .replace("hours", "h")
            .replace("hour", "h")
            .replace("hrs", "h")
            .replace("hr", "h")
            .replace("seconds", "s")
            .replace("second", "s")
            .replace("secs", "s")
            .replace("sec", "s")
            .replace("days", "d")
            .replace("day", "d")
        )

        m_dur = re.match(r"^((?:\d+\s*[smhd]\s*)+|\d+)\s*(.*)$", norm)
        if not m_dur:
            return None, None
        dur_part = "".join(m_dur.group(1).split())
        body = (m_dur.group(2) or "").strip() or None
        ms = self._parse_delay_to_ms(dur_part)
        return ms, body

    def _notify(self, title: str, body: str) -> None:
        exec_shell_command_async(
            [
                "notify-send",
                title,
                body,
                "-a",
                data.APP_NAME,
                "-e",
            ]
        )
