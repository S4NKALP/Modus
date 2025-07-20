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

        # In-memory cache
        self._scripts_cache: Dict[str, Dict] = {}
        self._last_cache_update = 0
        self._cache_update_interval = 300  # 5 minutes

        # Background cache building
        self._cache_building = False
        self._cache_thread = None

    def initialize(self):
        """Initialize the bash scripts plugin."""
        self.set_triggers(["sh"])
        self._load_scripts_cache()
        self._start_background_cache_update()

    def cleanup(self):
        """Cleanup the bash scripts plugin."""
        self._scripts_cache.clear()
        if self._cache_thread and self._cache_thread.is_alive():
            # Note: We don't join the thread to avoid blocking cleanup
            pass



    def _load_scripts_cache(self):
        """Load scripts cache from JSON file."""
        try:
            if os.path.exists(self.scripts_cache_file):
                with open(self.scripts_cache_file, "r", encoding="utf-8") as f:
                    cache_data = json.load(f)
                    self._scripts_cache = cache_data.get("scripts", {})
                    self._last_cache_update = cache_data.get("last_update", 0)
                    print(f"BashScriptsPlugin: Loaded {len(self._scripts_cache)} scripts from cache")
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
            print(f"BashScriptsPlugin: Saved {len(self._scripts_cache)} scripts to cache")
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
            print("BashScriptsPlugin: Building scripts cache in background...")
            new_cache = {}

            # Preserve existing custom scripts from cache
            for script_name, script_info in self._scripts_cache.items():
                if script_info.get("type") == "custom":
                    script_path = script_info.get("path", "")
                    if os.path.exists(script_path):
                        new_cache[script_name] = script_info

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

            print(f"BashScriptsPlugin: Background cache update completed. Found {len(self._scripts_cache)} scripts")

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

        # Handle special commands
        if not query:
            # Show all scripts when no query
            results.extend(self._list_all_scripts())
        elif query.startswith("add "):
            # Add new script command
            results.extend(self._handle_add_command(query))
        elif query.startswith("remove") or query.startswith("delete"):
            # Remove script command (handles both "remove" and "remove script_name")
            results.extend(self._handle_remove_command(query))
        elif query.startswith("edit "):
            # Edit script command
            results.extend(self._handle_edit_command(query))
        else:
            # Search for scripts
            results.extend(self._search_scripts(query))

        return results

    def _list_all_scripts(self) -> List[Result]:
        """List all available scripts."""
        results = []
        max_results = 20

        # Add management commands at the top
        results.extend(self._get_management_commands())

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
                print(f"BashScriptsPlugin: Script not found: {script_path}")
                return

            if not script_info.get("executable", False):
                print(f"BashScriptsPlugin: Script is not executable: {script_path}")
                return

            # Build command
            command = [script_path] + script_args

            print(f"BashScriptsPlugin: Executing script: {' '.join(command)}")
            exec_shell_command_async(command)

        except Exception as e:
            print(f"BashScriptsPlugin: Error executing script '{script_name}': {e}")
            import traceback
            traceback.print_exc()

    def _get_management_commands(self) -> List[Result]:
        """Get management commands for the plugin."""
        commands = []

        results = []
        for cmd in commands:
            result = Result(
                title=cmd["title"],
                subtitle=cmd["subtitle"],
                icon_markup=cmd["icon"],
                action=self._create_management_action(cmd["command"]),
                relevance=cmd.get("relevance", 0.6),
                plugin_name=self.display_name,
                data={"command": cmd["command"]}
            )
            results.append(result)

        return results

    def _create_management_action(self, command: str):
        """Create an action function for management commands."""
        def action():
            if command == "add":
                print("BashScriptsPlugin: Use 'add <script_name> <script_path>' to add a script")
        return action

    def _handle_add_command(self, query: str) -> List[Result]:
        """Handle add script command."""
        parts = query.split(" ", 2)
        if len(parts) < 3:
            return [Result(
                title="Add Script Usage",
                subtitle="Usage: add <script_name> <script_path> [description]",
                icon_markup=icons.info,
                action=lambda: None,
                relevance=1.0,
                plugin_name=self.display_name
            )]

        script_name = parts[1]
        script_path = os.path.expanduser(parts[2])
        description = parts[3] if len(parts) > 3 else f"Custom script: {script_name}"

        return [Result(
            title=f"Add Script: {script_name}",
            subtitle=f"Add {script_path} as '{script_name}'",
            icon_markup=icons.plus,
            action=lambda: self._add_custom_script(script_name, script_path, description),
            relevance=1.0,
            plugin_name=self.display_name
        )]

    def _handle_remove_command(self, query: str) -> List[Result]:
        """Handle remove script command."""
        parts = query.split(" ", 1)

        if len(parts) < 2 or (len(parts) == 2 and not parts[1].strip()):
            # Show all removable scripts (custom scripts from cache)
            results = []
            custom_scripts = {name: info for name, info in self._scripts_cache.items()
                            if info.get("type") == "custom"}

            if not custom_scripts:
                return [Result(
                    title="No Custom Scripts to Remove",
                    subtitle="No custom scripts found in collection",
                    icon_markup=icons.info,
                    action=lambda: None,
                    relevance=1.0,
                    plugin_name=self.display_name
                )]

            # Show each custom script as removable
            for script_name, script_info in custom_scripts.items():
                result = Result(
                    title=f"Remove: {script_name}",
                    subtitle=f"Remove custom script: {script_info.get('description', script_name)}",
                    icon_markup=icons.trash,
                    action=lambda sn=script_name: self._remove_custom_script(sn),
                    relevance=0.9,
                    plugin_name=self.display_name,
                    data={"script_name": script_name, "type": "remove_action"}
                )
                results.append(result)

            return results

        script_name = parts[1].strip()

        if script_name in self._scripts_cache:
            script_info = self._scripts_cache[script_name]
            if script_info.get("type") == "custom":
                return [Result(
                    title=f"Remove Script: {script_name}",
                    subtitle=f"Remove custom script '{script_name}' from collection",
                    icon_markup=icons.trash,
                    action=lambda: self._remove_custom_script(script_name),
                    relevance=1.0,
                    plugin_name=self.display_name
                )]
            else:
                return [Result(
                    title=f"Cannot Remove: {script_name}",
                    subtitle="Cannot remove discovered scripts (only custom scripts can be removed)",
                    icon_markup=icons.alert,
                    action=lambda: None,
                    relevance=1.0,
                    plugin_name=self.display_name
                )]
        else:
            return [Result(
                title=f"Script Not Found: {script_name}",
                subtitle="Script not found in collection",
                icon_markup=icons.alert,
                action=lambda: None,
                relevance=1.0,
                plugin_name=self.display_name
            )]

    def _handle_edit_command(self, query: str) -> List[Result]:
        """Handle edit script command."""
        parts = query.split(" ", 1)
        if len(parts) < 2:
            return [Result(
                title="Edit Script Usage",
                subtitle="Usage: edit <script_name>",
                icon_markup=icons.info,
                action=lambda: None,
                relevance=1.0,
                plugin_name=self.display_name
            )]

        script_name = parts[1]

        if script_name in self._scripts_cache:
            script_info = self._scripts_cache[script_name]
            script_path = script_info.get("path", "")
            return [Result(
                title=f"Edit Script: {script_name}",
                subtitle=f"Edit {script_path}",
                icon_markup=icons.config,
                action=lambda: self._edit_script(script_path),
                relevance=1.0,
                plugin_name=self.display_name
            )]
        else:
            return [Result(
                title=f"Script Not Found: {script_name}",
                subtitle="Script not found in collection",
                icon_markup=icons.alert,
                action=lambda: None,
                relevance=1.0,
                plugin_name=self.display_name
            )]



    def _add_custom_script(self, script_name: str, script_path: str, description: str):
        """Add a custom script directly to the cache."""
        try:
            if not os.path.exists(script_path):
                print(f"BashScriptsPlugin: Script file does not exist: {script_path}")
                return

            # Add directly to cache
            self._scripts_cache[script_name] = {
                "path": script_path,
                "name": script_name,
                "description": description,
                "type": "custom",
                "executable": os.access(script_path, os.X_OK),
                "args": [],
                "category": "custom"
            }

            # Save cache to persist the custom script
            self._save_scripts_cache()

            print(f"BashScriptsPlugin: Added custom script '{script_name}' -> {script_path}")

        except Exception as e:
            print(f"BashScriptsPlugin: Error adding custom script: {e}")

    def _remove_custom_script(self, script_name: str):
        """Remove a custom script from the cache."""
        try:
            # Remove from cache
            if script_name in self._scripts_cache:
                script_info = self._scripts_cache[script_name]
                if script_info.get("type") == "custom":
                    del self._scripts_cache[script_name]
                    # Save cache to persist the removal
                    self._save_scripts_cache()
                    print(f"BashScriptsPlugin: Removed custom script '{script_name}'")
                else:
                    print(f"BashScriptsPlugin: Cannot remove discovered script '{script_name}' (not a custom script)")
            else:
                print(f"BashScriptsPlugin: Script '{script_name}' not found")

        except Exception as e:
            print(f"BashScriptsPlugin: Error removing custom script: {e}")

    def _edit_script(self, script_path: str):
        """Open a script for editing."""
        try:
            if not os.path.exists(script_path):
                print(f"BashScriptsPlugin: Script file does not exist: {script_path}")
                return

            # Open with default editor
            editor = os.environ.get('EDITOR', 'nano')
            exec_shell_command_async([editor, script_path])
            print(f"BashScriptsPlugin: Opening script {script_path} with {editor}")

        except Exception as e:
            print(f"BashScriptsPlugin: Error opening script for editing: {e}")
