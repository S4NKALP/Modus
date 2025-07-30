import json
import os
import threading
import time
from typing import Dict, List

from fabric.utils import exec_shell_command_async

import config.data as data
import utils.icons as icons
from modules.launcher.plugin_base import PluginBase
from modules.launcher.result import Result


class BashScriptsPlugin(PluginBase):
    """
    Plugin for managing and executing bash scripts.
    """

    def __init__(self):
        super().__init__()
        self.display_name = "Bash Scripts"
        self.description = "Manage and execute bash scripts"

        # Configuration
        self.scripts_cache_file = os.path.join(data.CACHE_DIR, "bash_scripts.json")

        # Default script directory to scan (only Modus scripts)
        self.modus_scripts_dir = os.path.expanduser("~/.config/Modus/scripts")

        # Scripts to exclude from discovery
        self.excluded_scripts = {
            "screen-capture.sh"  # Exclude screen-capture.sh as it's handled by screencapture plugin
        }

        # Built-in power manager commands
        self.power_manager_commands = {
            "pm balanced": {
                "description": "Switch to balanced power profile",
                "profile": "balanced",
                "icon": icons.power_balanced,
            },
            "pm performance": {
                "description": "Switch to performance power profile",
                "profile": "performance",
                "icon": icons.power_performance,
            },
            "pm saver": {
                "description": "Switch to power saver profile",
                "profile": "power-saver",
                "icon": icons.power_saving,
            },
        }

        # In-memory cache
        self._scripts_cache: Dict[str, Dict] = {}
        self._last_cache_update = 0
        self._cache_update_interval = 300  # 5 minutes

        # Background cache building
        self._cache_building = False
        self._cache_thread = None

        # Battery service reference
        self._battery_service = None

    def initialize(self):
        """Initialize the bash scripts plugin."""
        self.set_triggers(["sh"])
        self._load_scripts_cache()
        self._start_background_cache_update()
        self._get_battery_service()

    def cleanup(self):
        """Cleanup the bash scripts plugin."""
        self._scripts_cache.clear()
        if self._cache_thread and self._cache_thread.is_alive():
            # Note: We don't join the thread to avoid blocking cleanup
            pass

    def _get_battery_service(self):
        """Get reference to the battery service."""
        try:
            from services.battery import Battery
            self._battery_service = Battery()
        except Exception as e:
            print(f"BashScriptsPlugin: Error getting battery service: {e}")
            self._battery_service = None

    def _set_power_profile(self, profile: str) -> bool:
        """Set the power profile using the battery service."""
        if not self._battery_service:
            print("BashScriptsPlugin: Battery service not available")
            return False

        try:
            # Check if profile proxy is available
            if not hasattr(self._battery_service, '_profile_proxy') or not self._battery_service._profile_proxy:
                print("BashScriptsPlugin: Power profile proxy not available")
                return False

            # Get available profiles
            profiles = self._battery_service._profile_proxy.Profiles
            available_profiles = []
            for p in profiles:
                if isinstance(p, dict) and "Profile" in p:
                    available_profiles.append(p["Profile"])
                elif hasattr(p, "Profile"):
                    available_profiles.append(p.Profile)
                elif isinstance(p, str):
                    available_profiles.append(p)

            # Map profile types to actual profile names
            profile_mapping = {
                "power-saver": ["power-saver", "powersave", "power_saver"],
                "balanced": ["balanced", "balance"],
                "performance": ["performance", "performance-mode"]
            }

            # Find the actual profile name
            actual_profile = None
            if profile in profile_mapping:
                for candidate in profile_mapping[profile]:
                    if candidate in available_profiles:
                        actual_profile = candidate
                        break
            elif profile in available_profiles:
                actual_profile = profile

            if actual_profile:
                self._battery_service._profile_proxy.ActiveProfile = actual_profile
                print(f"BashScriptsPlugin: Successfully set power profile to {actual_profile}")
                return True
            else:
                print(f"BashScriptsPlugin: No matching profile found for '{profile}' in available profiles: {available_profiles}")
                return False

        except Exception as e:
            print(f"BashScriptsPlugin: Error setting power profile: {e}")
            return False



    def _load_scripts_cache(self):
        """Load scripts cache from JSON file."""
        try:
            if os.path.exists(self.scripts_cache_file):
                with open(self.scripts_cache_file, "r", encoding="utf-8") as f:
                    cache_data = json.load(f)
                    self._scripts_cache = cache_data.get("scripts", {})
                    self._last_cache_update = cache_data.get("last_update", 0)
            else:
                print("BashScriptsPlugin: No cache file found, will build cache in background")
        except Exception as e:
            print(f"BashScriptsPlugin: Error loading scripts cache: {e}")
            self._scripts_cache = {}
            self._last_cache_update = 0

    def _save_scripts_cache(self):
        """Save scripts cache to JSON file."""
        try:
            os.makedirs(data.CACHE_DIR, exist_ok=True)
            cache_data = {
                "scripts": self._scripts_cache,
                "last_update": self._last_cache_update,
            }
            with open(self.scripts_cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2)
        except Exception as e:
            print(f"BashScriptsPlugin: Error saving scripts cache: {e}")

    def _start_background_cache_update(self):
        """Start background thread to update scripts cache."""
        current_time = time.time()
        
        # Check if cache needs updating
        if (current_time - self._last_cache_update > self._cache_update_interval or
            not self._scripts_cache):
            
            if not self._cache_building:
                self._cache_building = True
                self._cache_thread = threading.Thread(
                    target=self._build_scripts_cache_background,
                    daemon=True
                )
                self._cache_thread.start()

    def _build_scripts_cache_background(self):
        """Build scripts cache in background thread."""
        try:

            new_cache = {}

            # Scan Modus scripts directory for discovered scripts
            if os.path.exists(self.modus_scripts_dir) and os.path.isdir(self.modus_scripts_dir):
                try:
                    self._scan_directory_for_scripts(self.modus_scripts_dir, new_cache)
                except (PermissionError, FileNotFoundError, OSError) as e:
                    print(f"BashScriptsPlugin: Error scanning Modus scripts directory: {e}")

            # Update cache atomically
            self._scripts_cache = new_cache
            self._last_cache_update = time.time()

            # Save to disk
            self._save_scripts_cache()

        except Exception as e:
            print(f"BashScriptsPlugin: Error building scripts cache: {e}")
        finally:
            self._cache_building = False

    def _scan_directory_for_scripts(self, directory: str, cache: Dict):
        """Scan a directory for bash scripts and add them to cache."""
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if entry.is_file(follow_symlinks=False):
                        script_path = entry.path
                        script_name = entry.name

                        # Skip excluded scripts
                        if script_name in self.excluded_scripts:
                            continue

                        # Check if it's a script file
                        if self._is_script_file(script_path):
                            cache[script_name] = {
                                "path": script_path,
                                "name": script_name,
                                "description": self._get_script_description(script_path),
                                "type": "discovered",
                                "executable": os.access(script_path, os.X_OK),
                                "args": [],
                                "category": os.path.basename(directory)
                            }

        except (PermissionError, FileNotFoundError, OSError) as e:
            print(f"BashScriptsPlugin: Error scanning directory {directory}: {e}")
        except Exception as e:
            print(f"BashScriptsPlugin: Unexpected error scanning {directory}: {e}")

    def _is_script_file(self, file_path: str) -> bool:
        """Check if a file is a bash script."""
        try:
            # Check file extension first (most common case)
            if file_path.endswith(('.sh', '.bash')):
                return True

            # For files without extension, check shebang
            try:
                with open(file_path, 'rb') as f:
                    first_line = f.readline(100).decode('utf-8', errors='ignore')
                    if first_line.startswith('#!') and ('bash' in first_line or 'sh' in first_line):
                        return True
            except (PermissionError, FileNotFoundError, UnicodeDecodeError):
                pass

            return False
        except Exception:
            return False

    def _get_script_description(self, script_path: str) -> str:
        """Extract description from script comments."""
        try:
            with open(script_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

                # Look for description in first few comment lines
                for line in lines[:10]:
                    line = line.strip()
                    if line.startswith('#') and not line.startswith('#!'):
                        # Remove leading # and whitespace
                        desc = line[1:].strip()
                        if desc and len(desc) > 5:  # Meaningful description
                            return desc

                return f"Script: {os.path.basename(script_path)}"
        except (PermissionError, FileNotFoundError, UnicodeDecodeError):
            return f"Script: {os.path.basename(script_path)}"

    def query(self, query_string: str) -> List[Result]:
        """Search for bash scripts matching the query."""
        query = query_string.strip()

        # Start background update if needed (non-blocking)
        if not self._scripts_cache or (time.time() - self._last_cache_update > self._cache_update_interval):
            self._start_background_cache_update()

        results = []

        # Check for power manager commands first
        power_results = self._search_power_commands(query)
        if power_results:
            results.extend(power_results)

        # Handle special commands
        if not query:
            # Show all scripts when no query
            results.extend(self._list_all_scripts())
            # Also show power manager commands when no query
            if not power_results:
                results.extend(self._list_all_power_commands())
        else:
            # Search for scripts
            results.extend(self._search_scripts(query))

        return results

    def _list_all_scripts(self) -> List[Result]:
        """List all available scripts."""
        results = []
        max_results = 20

        # Sort scripts by name for consistent ordering
        sorted_scripts = sorted(self._scripts_cache.items(), key=lambda x: x[1].get("name", ""))

        # Add scripts (limit to max_results)
        for script_name, script_info in sorted_scripts:
            script_results = self._create_script_results_with_args(script_name, script_info, 0.8)
            for script_result in script_results:
                if len(results) < max_results:
                    results.append(script_result)
                else:
                    break
            if len(results) >= max_results:
                break

        return results

    def _search_scripts(self, query: str) -> List[Result]:
        """Search for scripts matching the query."""
        results = []
        query_lower = query.lower()
        max_results = 15

        # Categorize matches for better sorting
        exact_matches = []
        prefix_matches = []
        partial_matches = []
        description_matches = []

        for script_name, script_info in self._scripts_cache.items():
            script_name_lower = script_name.lower()
            description_lower = script_info.get("description", "").lower()

            # Skip if no match at all
            if query_lower not in script_name_lower and query_lower not in description_lower:
                continue

            # Categorize matches
            if script_name_lower == query_lower:
                exact_matches.append((script_name, script_info, 1.0))
            elif script_name_lower.startswith(query_lower):
                prefix_matches.append((script_name, script_info, 0.9))
            elif query_lower in script_name_lower:
                partial_matches.append((script_name, script_info, 0.7))
            elif query_lower in description_lower:
                description_matches.append((script_name, script_info, 0.5))

        # Combine results in priority order
        all_matches = exact_matches + prefix_matches + partial_matches + description_matches

        # Convert to Result objects
        for script_name, script_info, relevance in all_matches:
            script_results = self._create_script_results_with_args(script_name, script_info, relevance)
            for script_result in script_results:
                if len(results) < max_results:
                    results.append(script_result)
                else:
                    break
            if len(results) >= max_results:
                break

        return results

    def _search_power_commands(self, query: str) -> List[Result]:
        """Search for power manager commands matching the query."""
        if not query:
            return []

        results = []
        query_lower = query.lower()

        for cmd, info in self.power_manager_commands.items():
            cmd_lower = cmd.lower()
            description_lower = info["description"].lower()

            # Check for exact match or partial match
            if (query_lower == cmd_lower or
                cmd_lower.startswith(query_lower) or
                query_lower in cmd_lower or
                query_lower in description_lower):

                relevance = 1.0 if query_lower == cmd_lower else 0.9

                result = Result(
                    title=cmd,
                    subtitle=info["description"],
                    icon_markup=info["icon"],
                    action=self._create_power_action(info["profile"]),
                    relevance=relevance,
                    plugin_name=self.display_name,
                    data={"command": cmd, "profile": info["profile"], "type": "power_manager"}
                )
                results.append(result)

        return results

    def _list_all_power_commands(self) -> List[Result]:
        """List all power manager commands."""
        results = []

        for cmd, info in self.power_manager_commands.items():
            result = Result(
                title=cmd,
                subtitle=info["description"],
                icon_markup=info["icon"],
                action=self._create_power_action(info["profile"]),
                relevance=0.8,
                plugin_name=self.display_name,
                data={"command": cmd, "profile": info["profile"], "type": "power_manager"}
            )
            results.append(result)

        return results

    def _create_power_action(self, profile: str):
        """Create an action function for setting power profile."""
        def action():
            success = self._set_power_profile(profile)
            if success:
                # Clear the search query after successful execution
                try:
                    from fabric import Application
                    from gi.repository import GLib

                    app = Application.get_default()
                    if app and hasattr(app, "launcher"):
                        launcher = app.launcher
                        if launcher and hasattr(launcher, "search_entry"):
                            def clear_search():
                                launcher.search_entry.set_text("")
                                return False
                            # Use a small delay to ensure the action completes first
                            GLib.timeout_add(50, clear_search)
                except Exception as e:
                    print(f"BashScriptsPlugin: Could not clear search query: {e}")
        return action

    def _create_script_result(self, script_name: str, script_info: Dict, relevance: float) -> Result:
        """Create a Result object for a script."""
        script_path = script_info.get("path", "")
        description = script_info.get("description", "")
        script_type = script_info.get("type", "discovered")
        executable = script_info.get("executable", False)
        category = script_info.get("category", "")

        # Create subtitle with additional info
        subtitle_parts = []
        if description:
            subtitle_parts.append(description)
        if category:
            subtitle_parts.append(f"[{category}]")
        if not executable:
            subtitle_parts.append("(not executable)")

        subtitle = " | ".join(subtitle_parts) if subtitle_parts else f"Execute: {script_name}"

        # Choose icon based on script type and status
        if not executable:
            icon_markup = icons.file
        elif script_type == "custom":
            icon_markup = icons.star
        else:
            icon_markup = icons.terminal

        return Result(
            title=script_name,
            subtitle=subtitle,
            icon_markup=icon_markup,
            action=self._create_script_action(script_name, script_info),
            relevance=relevance,
            plugin_name=self.display_name,
            data={"script_name": script_name, "script_path": script_path, "type": script_type}
        )

    def _create_script_results_with_args(self, script_name: str, script_info: Dict, relevance: float) -> List[Result]:
        """Create multiple Result objects for scripts that support arguments."""
        results = []

        # Check for special scripts that need argument variants
        if script_name == "hyprpicker.sh":
            # For hyprpicker, only show the argument variants (skip basic version)
            variants = [
                ("-rgb", "Pick RGB color"),
                ("-hex", "Pick HEX color"),
                ("-hsv", "Pick HSV color")
            ]

            for arg, desc in variants:
                variant_result = Result(
                    title=f"{script_name} {arg}",
                    subtitle=f"{desc} | [scripts]",
                    icon_markup=icons.terminal,
                    action=self._create_script_action_with_args(script_name, script_info, [arg]),
                    relevance=relevance + 0.1,  # Slightly higher relevance for specific variants
                    plugin_name=self.display_name,
                    data={"script_name": script_name, "script_path": script_info.get("path", ""), "type": script_info.get("type", "discovered"), "args": [arg]}
                )
                results.append(variant_result)
        else:
            # For other scripts, create the basic result
            basic_result = self._create_script_result(script_name, script_info, relevance)
            results.append(basic_result)

        return results

    def _create_script_action(self, script_name: str, script_info: Dict):
        """Create an action function for executing a script."""
        def action():
            self._execute_script(script_name, script_info)
        return action

    def _create_script_action_with_args(self, script_name: str, script_info: Dict, args: List[str]):
        """Create an action function for executing a script with specific arguments."""
        def action():
            # Create a modified script_info with the specific arguments
            modified_script_info = script_info.copy()
            modified_script_info["args"] = args
            self._execute_script(script_name, modified_script_info)
        return action

    def _execute_script(self, script_name: str, script_info: Dict):
        """Execute a bash script."""
        try:
            script_path = script_info.get("path", "")
            script_args = script_info.get("args", [])

            if not os.path.exists(script_path):
                return

            if not script_info.get("executable", False):
                return

            # Build command
            command = [script_path] + script_args
            exec_shell_command_async(command)

        except Exception as e:
            print(f"BashScriptsPlugin: Error executing script '{script_name}': {e}")

