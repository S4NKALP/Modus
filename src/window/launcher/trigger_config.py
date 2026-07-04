from typing import Any, Dict, List

import tomlkit
from fabric.utils import get_relative_path


class TriggerConfig:
    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = get_relative_path("../../../config/launcher.toml")

        self.config_path = config_path

        config = {"launcher_config": {}, "settings": {}}
        try:
            with open(config_path, "r") as f:
                data = tomlkit.load(f)
                config["launcher_config"] = dict(data.get("launcher_config", {}))
                config["settings"] = dict(data.get("settings", {}))
        except FileNotFoundError:
            pass
        except Exception as e:
            from fabric.utils import logger

            logger.error(f"Error loading trigger config: {e}")

        self.config = config
        self.launcher_config = self.config.get("launcher_config", {})

        # Initialize settings with defaults
        default_settings = {
            "max_examples_shown": 2,
            "default_icon": "application-default-icon",
            "fallback_example_template": "{trigger} <search>",
            "config_version": "1.0",
        }
        self.settings = {**default_settings, **self.config.get("settings", {})}

    def get_trigger_examples(self, trigger: str) -> List[str]:
        examples = self.launcher_config.get(trigger, {}).get("examples", [])
        if not examples:
            template = self.settings.get(
                "fallback_example_template", "{trigger} <search>"
            )
            examples = [template.format(trigger=trigger)]
        return examples

    def get_trigger_icon(self, trigger: str) -> str:
        icon = self.launcher_config.get(trigger, {}).get(
            "icon", self.settings.get("default_icon", "application-default-icon")
        )
        return icon

    def get_trigger_description(self, trigger: str) -> str:
        return self.launcher_config.get(trigger, {}).get(
            "description", f"{trigger} - No description available"
        )

    def get_all_triggers(self) -> Dict[str, Dict[str, Any]]:
        return self.launcher_config.copy()
