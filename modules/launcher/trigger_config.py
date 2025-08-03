import json
import os
from typing import Any, Dict, List

from fabric.utils import get_relative_path


class TriggerConfig:
    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = get_relative_path("../../config/assets/launcher.json")

        self.config_path = config_path

        # Load configuration from JSON file
        config = {"launcher_config": {}, "settings": {}}
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except Exception as e:
                print(f"Error loading trigger config: {e}")

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
