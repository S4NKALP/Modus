"""
Simple trigger configuration manager for the launcher.
"""

import json
import os
from typing import Any, Dict, List

import utils.icons as icons
from fabric.utils import get_relative_path


def load_launcher_config(config_path: str) -> Dict:
    """Load trigger configuration from JSON file"""
    config = {"launcher_config": {}, "settings": {}}

    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception as e:
            print(f"Error loading trigger config: {e}")

    return config


def save_launcher_config(config_path: str, config: Dict) -> bool:
    """Save trigger configuration to JSON file"""
    try:
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving trigger config: {e}")
        return False


class TriggerConfig:
    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = get_relative_path("../../config/launcher.json")

        self.config_path = config_path
        self.config = load_launcher_config(config_path)
        self.launcher_config = self.config.get("launcher_config", {})
        self.settings = self.config.get("settings", {})

        if not self.launcher_config:
            self._create_default_config()

    def save_config(self) -> bool:
        self.config["launcher_config"] = self.launcher_config
        self.config["settings"] = self.settings
        return save_launcher_config(self.config_path, self.config)

    def get_trigger_examples(self, trigger: str) -> List[str]:
        examples = self.launcher_config.get(trigger, {}).get("examples", [])
        if not examples:
            template = self.settings.get(
                "fallback_example_template", "{trigger} <search>"
            )
            examples = [template.format(trigger=trigger)]
        return examples

    def get_trigger_icon(self, trigger: str) -> str:
        icon_name = self.launcher_config.get(trigger, {}).get(
            "icon", self.settings.get("default_icon", "apps")
        )
        return getattr(icons, icon_name, icons.apps)

    def get_trigger_description(self, trigger: str) -> str:
        return self.launcher_config.get(trigger, {}).get(
            "description", f"{trigger} - No description available"
        )

    def get_all_triggers(self) -> Dict[str, Dict[str, Any]]:
        return self.launcher_config.copy()

    def add_trigger(
        self,
        trigger: str,
        examples: List[str],
        icon: str = None,
        description: str = None,
    ) -> bool:
        try:
            self.launcher_config[trigger] = {
                "examples": examples,
                "icon": icon or self.settings.get("default_icon", "system-search"),
                "description": description or f"{trigger} - Custom trigger",
            }
            return True
        except Exception as e:
            print(f"Error adding trigger {trigger}: {e}")
            return False

    def remove_trigger(self, trigger: str) -> bool:
        try:
            if trigger in self.launcher_config:
                del self.launcher_config[trigger]
                return True
            return False
        except Exception as e:
            print(f"Error removing trigger {trigger}: {e}")
            return False

    def get_max_examples_shown(self) -> int:
        return self.settings.get("max_examples_shown", 2)

    def _create_default_config(self):
        self.launcher_config = {
            "app": {
                "examples": ["app firefox", "app chrome", "app terminal"],
                "icon": "apps",
                "description": "Applications - Launch installed applications",
            },
            "calc": {
                "examples": ["calc 2+2", "calc sqrt(16)", "calc pi*2"],
                "icon": "calculator",
                "description": "Calculator - Perform mathematical calculations",
            },
            "file": {
                "examples": ["file document.pdf", "file *.py", "file config"],
                "icon": "file",
                "description": "Files - Search for files and documents",
            },
        }

        self.settings = {
            "max_examples_shown": 2,
            "default_icon": "apps",
            "fallback_example_template": "{trigger} <search>",
            "config_version": "1.0",
        }
