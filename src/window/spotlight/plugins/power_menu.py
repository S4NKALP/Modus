from typing import Any

from fabric.utils import exec_shell_command_async

from window.spotlight.api import SearchResult, SpotlightPlugin


class PowerMenuPlugin(SpotlightPlugin):
    id = "power_menu"
    name = "Power Menu"
    icon = "system-shutdown-symbolic"
    keywords = ["powermenu", "pm"]
    searchable = True
    priority = 95

    POWER_OPTIONS = [
        {
            "id": "shutdown",
            "name": "Shutdown",
            "icon": "system-shutdown",
            "command": "systemctl poweroff",
            "description": "Shutdown the system",
        },
        {
            "id": "restart",
            "name": "Restart",
            "icon": "system-reboot",
            "command": "systemctl reboot",
            "description": "Restart the system",
        },
        {
            "id": "suspend",
            "name": "Suspend",
            "icon": "system-suspend",
            "command": "systemctl suspend",
            "description": "Suspend the system to RAM",
        },
        {
            "id": "hibernate",
            "name": "Hibernate",
            "icon": "system-hibernate",
            "command": "systemctl hibernate",
            "description": "Hibernate the system to disk",
        },
        {
            "id": "logout",
            "name": "Logout",
            "icon": "system-log-out",
            "command": "pkill -SIGTERM Hyprland",
            "description": "Logout from the current session",
        },
        {
            "id": "lock",
            "name": "Lock Screen",
            "icon": "system-lock-screen",
            "command": 'fabric-cli exec modus "lock_screen.lock()"',
            "description": "Lock the screen",
        },
    ]

    def initialize(self) -> None:
        pass

    def cleanup(self) -> None:
        pass

    def search(self, query: str, token: Any) -> list[SearchResult]:
        q = query.lower().strip()
        if not q:
            return []

        for prefix in ("powermenu ", "pm "):
            if q.startswith(prefix):
                q = q[len(prefix) :].strip()
                break
        if q in ("powermenu", "pm"):
            q = ""

        if not q:
            return [
                SearchResult(
                    id=f"power_{option['id']}",
                    title=option["name"],
                    subtitle=option["description"],
                    icon_name=option["icon"],
                    score=100.0 - i,
                    render_type="power",
                    action=lambda cmd=option["command"]: exec_shell_command_async(cmd),
                    metadata={"power_option": option},
                )
                for i, option in enumerate(self.POWER_OPTIONS)
            ]

        results: list[SearchResult] = []

        for option in self.POWER_OPTIONS:
            score = 0.0
            name = option["name"].lower()
            desc = option["description"].lower()

            if q == name:
                score = 100.0
            elif name.startswith(q):
                score = 90.0
            elif len(q) >= 3 and q in name:
                score = 80.0
            elif len(q) >= 3 and q in desc:
                score = 60.0

            if score > 0:
                results.append(
                    SearchResult(
                        id=f"power_{option['id']}",
                        title=option["name"],
                        subtitle=option["description"],
                        icon_name=option["icon"],
                        score=score,
                        render_type="power",
                        action=lambda cmd=option["command"]: exec_shell_command_async(
                            cmd
                        ),
                        metadata={"power_option": option},
                    )
                )

        results.sort(key=lambda r: r.score, reverse=True)
        return results

    def handle_external(self, command: str, args: str) -> None:
        if not args:
            return
        for option in self.POWER_OPTIONS:
            if args.lower() == option["name"].lower():
                exec_shell_command_async(option["command"])
                return


PLUGIN = PowerMenuPlugin
