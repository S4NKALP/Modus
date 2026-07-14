import os
import signal
import subprocess

from fabric.utils import logger

from utils.functions import format_duration, parse_timeout_string
from window.spotlight.api import SearchResult, SpotlightPlugin

_PID_FILE = os.path.join(
    os.environ.get("XDG_RUNTIME_DIR") or "/tmp", "modus-caffeine.pid"
)
_INHIBIT_WHAT = "idle:sleep"
_INHIBIT_WHY = "Modus Caffeine"
# Spotlight exits on dismiss, so we pin an effectively infinite sleep for
# indefinite mode instead of relying on an in-process timer.
_INDEFINITE_SECS = 100_000_000


class CaffeinePlugin(SpotlightPlugin):
    id = "caffeine"
    name = "Caffeine"
    icon = "user-available-symbolic"
    keywords = ["caffeine", "caff"]
    searchable = True
    priority = 90

    def initialize(self) -> None:
        pass

    def cleanup(self) -> None:
        pass

    # --- state helpers -------------------------------------------------

    def _read_pid(self) -> int | None:
        try:
            with open(_PID_FILE) as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            return None

    def _is_our_pid(self, pid: int) -> bool:
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                data = f.read().decode(errors="ignore")
            return "systemd-inhibit" in data and _INHIBIT_WHY in data
        except OSError:
            return False

    def _write_pid(self, pid: int) -> None:
        try:
            with open(_PID_FILE, "w") as f:
                f.write(str(pid))
        except OSError as e:
            logger.warning(f"[Caffeine] cannot record pid: {e}")

    def _kill_existing(self) -> None:
        pid = self._read_pid()
        if pid and self._is_our_pid(pid):
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        try:
            os.unlink(_PID_FILE)
        except OSError:
            pass

    # --- duration parsing ----------------------------------------------

    @staticmethod
    def _parse_duration(text: str) -> int | None:
        seconds = parse_timeout_string(text, in_seconds=True)
        return seconds if seconds != 5 else None  # 5 is the default on parse failure

    @staticmethod
    def _humanize(secs: int) -> str:
        result = format_duration(secs)
        # format_duration returns "N/A" for 0, but we want "0s"
        if result == "N/A":
            return "0s"
        # format_duration returns "Xh Ym" or "Xm", we want shorter format
        # For hours only: "1h" instead of "1h 0m"
        if "h" in result and "m" in result:
            hours = result.split("h")[0]
            return f"{hours}h"
        return result

    # --- inhibition ----------------------------------------------------

    def _spawn(self, seconds: int) -> None:
        self._kill_existing()
        cmd = [
            "systemd-inhibit",
            f"--what={_INHIBIT_WHAT}",
            f"--why={_INHIBIT_WHY}",
            "--mode=block",
            "sleep",
            str(seconds),
        ]
        try:
            proc = subprocess.Popen(cmd)
        except FileNotFoundError:
            logger.error("[Caffeine] systemd-inhibit not found on this system")
            return
        except Exception as e:
            logger.error(f"[Caffeine] failed to start inhibitor: {e}")
            return
        self._write_pid(proc.pid)

    def _apply(self, arg: str) -> None:
        arg = (arg or "").strip().lower()
        if arg in ("", "on"):
            self._spawn(_INDEFINITE_SECS)
            return
        if arg == "off":
            self._kill_existing()
            return
        secs = self._parse_duration(arg)
        if secs is not None:
            self._spawn(secs)
            return
        logger.warning(f"[Caffeine] unknown argument: {arg!r}")

    # --- search surface ------------------------------------------------

    def _result(
        self,
        rid: str,
        title: str,
        subtitle: str,
        action,
        active: bool,
    ) -> SearchResult:
        suffix = " — active" if active and rid != "caffeine_off" else ""
        return SearchResult(
            id=rid,
            title=title + suffix,
            subtitle=subtitle,
            icon_name="user-available-symbolic" if active else "user-away-symbolic",
            score=100.0,
            action=action,
            render_type="default",
            plugin_name=self.name,
            plugin_id=self.id,
        )

    def _mk(self, label: str, title: str, subtitle: str, active: bool) -> SearchResult:
        return self._result(
            f"caffeine_{label}",
            title,
            subtitle,
            (lambda a=label: self._apply(a)),
            active,
        )

    def _duration_subtitle(self, secs: int, active: bool) -> str:
        if active:
            return "Caffeine active — re-select to restart timer"
        return f"Inhibits idle/sleep for {self._humanize(secs)}"

    def _menu(self, active: bool) -> list[SearchResult]:
        presets = [("5m", 300), ("15m", 900), ("30m", 1800), ("1h", 3600)]
        results = [
            self._mk("on", "Enable Caffeine", "Stay awake until turned off", active),
            self._mk("off", "Disable Caffeine", "Allow idle and sleep again", active),
        ]
        results += [
            self._mk(
                label,
                f"Caffeine for {label}",
                self._duration_subtitle(secs, active),
                active,
            )
            for label, secs in presets
        ]
        return results

    def search(self, query: str, token) -> list[SearchResult]:
        q = query.strip().lower()
        for kw in ("caffeine ", "caff "):
            if q.startswith(kw):
                q = q[len(kw) :].strip()
                break

        active = self._read_pid() is not None

        if not q or q in ("caffeine", "caff"):
            return self._menu(active)

        if q == "off":
            return [
                self._mk(
                    "off", "Disable Caffeine", "Allow idle and sleep again", active
                )
            ]
        if q == "on":
            return [
                self._mk("on", "Enable Caffeine", "Stay awake until turned off", active)
            ]

        secs = self._parse_duration(q)
        if secs is not None:
            return [
                self._mk(
                    q,
                    f"Caffeine for {q}",
                    self._duration_subtitle(secs, active),
                    active,
                )
            ]

        return [
            self._result(
                "caffeine_help",
                "Caffeine",
                "Usage: caffeine on | off | <time> (e.g. 15m, 1hr)",
                None,
                active,
            )
        ]

    def detect(self, text: str) -> bool:
        t = text.strip().lower()
        if t in ("caffeine", "caff"):
            return True
        return self._parse_duration(t) is not None

    def handle_external(self, command: str, args: str) -> None:
        if command not in ("caffeine", "caff"):
            return
        self._apply(args.strip())


PLUGIN = CaffeinePlugin
