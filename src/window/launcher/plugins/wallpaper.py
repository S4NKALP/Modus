import hashlib
import threading

import tomlkit
from typing import Dict, List, Optional

from fabric.utils import (
    GdkPixbuf,
    GLib,
    exec_shell_command_async,
    logger,
    os,
    random,
    time,
)

import shared.data as data
from window.launcher.plugin_base import PluginBase
from window.launcher.result import Result


class WallpaperPlugin(PluginBase):
    """
    Plugin for wallpaper management with search, random selection, and matugen integration.
    """

    def __init__(self):
        super().__init__()
        self.display_name = "Wallpaper"
        self.wallpapers = []
        self.cache_dir = f"{data.CACHE_DIR}/thumbs"
        self.thumbnail_cache: Dict[str, Optional[GdkPixbuf.Pixbuf]] = {}
        self.thumbnail_loading = set()  # Track which thumbnails are being loaded
        self.schemes = {
            "scheme-tonal-spot": "Tonal Spot",
            "scheme-content": "Content",
            "scheme-expressive": "Expressive",
            "scheme-fidelity": "Fidelity",
            "scheme-fruit-salad": "Fruit Salad",
            "scheme-monochrome": "Monochrome",
            "scheme-neutral": "Neutral",
            "scheme-rainbow": "Rainbow",
        }

    def initialize(self):
        """Initialize the wallpaper plugin."""
        self.set_triggers(["wall"])
        self._load_wallpapers()
        os.makedirs(self.cache_dir, exist_ok=True)
        # Start background thumbnail creation
        self._start_background_thumbnail_creation()

    def cleanup(self):
        """Cleanup the wallpaper plugin."""
        pass

    def _load_wallpapers(self):
        """Load available wallpapers from the wallpapers directory."""
        try:
            if os.path.exists(data.WALLPAPERS_DIR):
                self.wallpapers = sorted(
                    [f for f in os.listdir(data.WALLPAPERS_DIR) if self._is_image(f)]
                )
            else:
                logger.error(f"Wallpapers directory not found: {data.WALLPAPERS_DIR}")
        except Exception as e:
            logger.error(f"Error loading wallpapers: {e}")

    def _is_image(self, filename: str) -> bool:
        """Check if file is a supported image format."""
        return filename.lower().endswith(
            (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")
        )

    def _get_matugen_state(self) -> bool:
        """Get current matugen state from config.toml."""
        self.matugen_enabled = True
        try:
            with open(data.CONFIG_FILE, "r") as f:
                config = tomlkit.load(f)
                self.matugen_enabled = config.get("matugen_enabled", True)
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.error(f"Error reading config file: {e}")

        return self.matugen_enabled

    def _set_matugen_state(self, enabled: bool):
        """Set matugen state and save to config.toml."""
        self.matugen_enabled = enabled
        try:
            config = {}
            if os.path.exists(data.CONFIG_FILE):
                with open(data.CONFIG_FILE, "r") as f:
                    config = tomlkit.load(f)

            config["matugen_enabled"] = enabled

            with open(data.CONFIG_FILE, "w") as f:
                tomlkit.dump(config, f)

        except Exception as e:
            logger.error(f"Error writing matugen state to config: {e}")

        # Clear the search query after toggling matugen
        self._clear_launcher_query()

        # # Send notification
        # status = "enabled" if enabled else "disabled"
        # exec_shell_command_async(
        #     f"notify-send '🎨 Matugen' 'Dynamic colors {status}' -a '{
        #         data.APP_NAME_CAP
        #     }' -e"
        # )

    def _clear_launcher_query(self):
        """Clear the launcher search query and reset to trigger."""
        try:
            # Try to access the launcher through the fabric Application

            from fabric import Application

            app = Application.get_default()

            if app and hasattr(app, "launcher"):
                launcher = app.launcher
                if launcher and hasattr(launcher, "search_entry"):

                    def clear_and_refresh():
                        # Clear the search entry to just the trigger
                        launcher.search_entry.set_text("wall ")
                        # Position cursor at the end
                        launcher.search_entry.set_position(-1)
                        # Trigger the search to show default wallpaper view
                        if hasattr(launcher, "_perform_search"):
                            launcher._perform_search("wall ")
                        return False

                    # Use a small delay to ensure the action completes first
                    GLib.timeout_add(50, clear_and_refresh)
                    return

            # Fallback: try to find launcher instance through other means
            import gc

            for obj in gc.get_objects():
                if hasattr(obj, "__class__") and obj.__class__.__name__ == "Launcher":
                    if hasattr(obj, "search_entry") and hasattr(obj, "_perform_search"):

                        def clear_and_refresh():
                            obj.search_entry.set_text("wall ")
                            obj.search_entry.set_position(-1)
                            obj._perform_search("wall ")
                            return False

                        GLib.timeout_add(50, clear_and_refresh)
                        return

        except Exception as e:
            logger.error(f"Could not clear launcher query: {e}")

    def _get_cache_path(self, filename: str) -> str:
        """Get cache path for wallpaper thumbnail."""
        file_hash = hashlib.md5(filename.encode("utf-8")).hexdigest()
        return os.path.join(self.cache_dir, f"{file_hash}.png")

    def _create_thumbnail(self, filename: str) -> str:
        """Create thumbnail for wallpaper if it doesn't exist."""
        full_path = os.path.join(data.WALLPAPERS_DIR, filename)
        cache_path = self._get_cache_path(filename)

        if not os.path.exists(cache_path):
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    full_path, 32, 32, True
                )
                pixbuf.savev(cache_path, "png", [], [])
            except Exception as e:
                logger.error(f"Error creating thumbnail for {filename}: {e}")
                return None

        return cache_path

    def _start_background_thumbnail_creation(self):
        """Start background thread to create thumbnails for all wallpapers."""

        def create_thumbnails():
            for wallpaper in self.wallpapers:
                if wallpaper not in self.thumbnail_loading:
                    self.thumbnail_loading.add(wallpaper)
                    try:
                        cache_path = self._create_thumbnail(wallpaper)
                        if cache_path and os.path.exists(cache_path):
                            # Load thumbnail into memory cache
                            try:
                                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                                    cache_path, 32, 32, True
                                )
                                self.thumbnail_cache[wallpaper] = pixbuf
                            except Exception as e:
                                logger.error(
                                    f"Error loading thumbnail for {wallpaper}: {e}"
                                )
                                self.thumbnail_cache[wallpaper] = None
                        else:
                            self.thumbnail_cache[wallpaper] = None
                    except Exception as e:
                        logger.error(f"Error processing thumbnail for {wallpaper}: {e}")
                        self.thumbnail_cache[wallpaper] = None
                    finally:
                        self.thumbnail_loading.discard(wallpaper)

                    # Small delay to prevent overwhelming the system
                    time.sleep(0.01)

        # Start background thread
        thread = threading.Thread(target=create_thumbnails, daemon=True)
        thread.start()

    def _get_thumbnail_fast(self, filename: str) -> Optional[GdkPixbuf.Pixbuf]:
        """Get thumbnail quickly from cache or return None if not ready."""
        # Return cached thumbnail if available
        if filename in self.thumbnail_cache:
            return self.thumbnail_cache[filename]

        # Check if thumbnail file exists and load it immediately
        cache_path = self._get_cache_path(filename)
        if os.path.exists(cache_path):
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    cache_path, 32, 32, True
                )
                self.thumbnail_cache[filename] = pixbuf
                return pixbuf
            except Exception as e:
                logger.error(f"Error loading thumbnail for {filename}: {e}")
                self.thumbnail_cache[filename] = None
                return None

        # If not in cache and file doesn't exist, trigger background creation
        if filename not in self.thumbnail_loading:
            self.thumbnail_loading.add(filename)

            def create_async():
                try:
                    cache_path = self._create_thumbnail(filename)
                    if cache_path and os.path.exists(cache_path):
                        try:
                            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                                cache_path, 32, 32, True
                            )
                            self.thumbnail_cache[filename] = pixbuf
                        except Exception as e:
                            logger.error(f"Error loading thumbnail for {filename}: {e}")
                            self.thumbnail_cache[filename] = None
                    else:
                        self.thumbnail_cache[filename] = None
                except Exception as e:
                    logger.error(f"Error creating thumbnail for {filename}: {e}")
                    self.thumbnail_cache[filename] = None
                finally:
                    self.thumbnail_loading.discard(filename)

            thread = threading.Thread(target=create_async, daemon=True)
            thread.start()

        return None

    def _set_wallpaper(self, filename: str, scheme: str = None):
        """Set wallpaper and apply matugen color scheme if enabled."""
        full_path = os.path.join(data.WALLPAPERS_DIR, filename)
        current_wall = os.path.expanduser("~/.current.wall")

        if scheme is None:
            scheme = self._get_current_scheme()

        # Update current wallpaper symlink
        if os.path.isfile(current_wall) or os.path.islink(current_wall):
            os.remove(current_wall)
        os.symlink(full_path, current_wall)

        # Always set the wallpaper image
        exec_shell_command_async(
            f'awww img "{
                full_path
            }" -t outer --transition-duration 1.5 --transition-step 255 --transition-fps 60 -f Nearest'
        )

        # If Matugen is enabled, also apply the color scheme
        matugen_enabled = self._get_matugen_state()
        if matugen_enabled:
            exec_shell_command_async(
                f'matugen image "{full_path}" -t {scheme} --source-color-index 0'
            )

    def _set_random_wallpaper(self):
        """Set a random wallpaper."""
        if not self.wallpapers:
            return

        filename = random.choice(self.wallpapers)
        self._set_wallpaper(filename)
        # Show notification for immediate feedback
        exec_shell_command_async(
            f"notify-send '🎲 Random Wallpaper' 'Applied: {filename}' -a '{
                data.APP_NAME_CAP
            }' -e"
        )
        return filename

    def _get_current_scheme(self) -> str:
        """Get current color scheme from config (default to tonal-spot)."""
        try:
            with open(data.CONFIG_FILE, "r") as f:
                config = tomlkit.load(f)
                return config.get("current_scheme", "scheme-tonal-spot")
        except FileNotFoundError:
            return "scheme-tonal-spot"
        except Exception as e:
            logger.error(f"Error reading current scheme from config: {e}")
            return "scheme-tonal-spot"

    def _set_current_scheme(self, scheme: str):
        """Set current color scheme and apply it."""
        scheme_name = self.schemes.get(scheme, scheme)
        matugen_enabled = self._get_matugen_state()

        try:
            config = tomlkit.document()
            if os.path.exists(data.CONFIG_FILE):
                with open(data.CONFIG_FILE, "r") as f:
                    config = tomlkit.load(f)

            config["current_scheme"] = scheme

            with open(data.CONFIG_FILE, "w") as f:
                tomlkit.dump(config, f)

        except Exception as e:
            logger.error(f"Error saving current scheme to config: {e}")
            return

        # Apply the scheme to current wallpaper if matugen is enabled
        if matugen_enabled:
            current_wall = os.path.expanduser("~/.current.wall")
            if os.path.exists(current_wall) and os.path.islink(current_wall):
                # Get the current wallpaper path
                wallpaper_path = os.readlink(current_wall)
                if os.path.exists(wallpaper_path):
                    # Apply the new scheme to current wallpaper
                    exec_shell_command_async(
                        f'matugen image "{wallpaper_path}" -t {scheme} --source-color-index 0'
                    )

                    # Send notification
                    exec_shell_command_async(
                        f"notify-send '🎨 Color Scheme' 'Applied {
                            scheme_name
                        } scheme' -a '{data.APP_NAME_CAP}' -e"
                    )
                else:
                    # No current wallpaper, just show scheme change notification
                    exec_shell_command_async(
                        f"notify-send '🎨 Color Scheme' 'Set to {
                            scheme_name
                        } (will apply to next wallpaper)' -a '{data.APP_NAME_CAP}' -e"
                    )
            else:
                # No current wallpaper, just show scheme change notification
                exec_shell_command_async(
                    f"notify-send '🎨 Color Scheme' 'Set to {
                        scheme_name
                    } (will apply to next wallpaper)' -a '{data.APP_NAME_CAP}' -e"
                )
        else:
            # Matugen is disabled, just save the setting
            exec_shell_command_async(
                f"notify-send '🎨 Color Scheme' 'Set to {
                    scheme_name
                } (matugen disabled)' -a '{data.APP_NAME_CAP}' -e"
            )

    def _get_status_indicators(self) -> tuple:
        """Get current status indicators for display."""
        current_scheme = self._get_current_scheme()
        matugen_enabled = self._get_matugen_state()
        scheme_name = self.schemes.get(current_scheme, current_scheme)

        indicators = []
        if not matugen_enabled:
            indicators.append("Matugen Off")

        indicator_text = " • " + " • ".join(indicators) if indicators else ""
        status_text = f"Matugen: {
            'Enabled' if matugen_enabled else 'Disabled'
        } • Scheme: {scheme_name}"

        return indicator_text, status_text, current_scheme, matugen_enabled

    def query(self, query_string: str) -> List[Result]:
        """Search wallpapers and provide management options."""
        results = []
        query = query_string.lower().strip()

        # Get status indicators for consistent display
        indicator_text, status_text, current_scheme, matugen_enabled = (
            self._get_status_indicators()
        )

        # Special commands
        if query.strip() == "random":
            # Show result for random wallpaper (execute on Enter)
            results.append(
                Result(
                    title=f"Random Wallpaper{indicator_text}",
                    subtitle=f"Set a random wallpaper • {status_text}",
                    icon_name="media-playlist-shuffle-symbolic",
                    action=lambda: self._set_random_wallpaper(),
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={
                        "action": "random",
                        "bypass_max_results": True,
                        "keep_launcher_open": True,
                    },
                )
            )
        elif query.startswith("random") and query.strip() != "random":
            # Show suggestion for random wallpaper (partial match)
            results.append(
                Result(
                    title=f"Random Wallpaper{indicator_text}",
                    subtitle=f"Set a random wallpaper • {status_text}",
                    icon_name="media-playlist-shuffle-symbolic",
                    action=lambda: self._set_random_wallpaper(),
                    relevance=0.9,
                    plugin_name=self.display_name,
                    data={
                        "action": "random_suggestion",
                        "bypass_max_results": True,
                        "keep_launcher_open": True,
                    },
                )
            )

        # Color scheme commands
        if "scheme" in query:
            current_scheme = self._get_current_scheme()
            matugen_enabled = self._get_matugen_state()

            # Show all available schemes
            for scheme_id, scheme_name in self.schemes.items():
                # Check if this scheme matches the query (for filtering)
                if query.strip() == "scheme":
                    # Show all schemes when just "scheme" is typed
                    scheme_matches = True
                else:
                    # Extract search terms from query (remove "scheme" keyword)
                    search_terms = query.replace("scheme", "").strip().split()
                    scheme_matches = False

                    # Check if any search term matches the scheme name or ID
                    for term in search_terms:
                        if (
                            term.lower() in scheme_name.lower()
                            or term.lower() in scheme_id.lower()
                        ):
                            scheme_matches = True
                            break

                if scheme_matches:
                    # Create indicators
                    indicators = []
                    if scheme_id == current_scheme:
                        indicators.append("Current")
                    if not matugen_enabled:
                        indicators.append("Matugen Off")

                    indicator_text = (
                        " • " + " • ".join(indicators) if indicators else ""
                    )

                    results.append(
                        Result(
                            title=f"{scheme_name}{indicator_text}",
                            subtitle=f"Set color scheme to {scheme_name}"
                            + (
                                " (requires matugen enabled)"
                                if not matugen_enabled
                                else ""
                            ),
                            icon_name="color-management-symbolic",
                            action=lambda s=scheme_id: self._set_current_scheme(s),
                            relevance=1.0 if scheme_id == current_scheme else 0.8,
                            plugin_name=self.display_name,
                            data={
                                "action": "scheme_select",
                                "scheme": scheme_id,
                                "bypass_max_results": True,
                                "keep_launcher_open": True,
                            },
                        )
                    )

        # Matugen controls
        if "matugen" in query:
            current_state = self._get_matugen_state()

            # Check for exact command matches
            if query.strip() == "matugen on" or query.strip() == "matugen enable":
                # Show result for enabling matugen (execute on Enter)
                results.append(
                    Result(
                        title=f"Enable Matugen{indicator_text}",
                        subtitle=f"Turn on dynamic color generation • {status_text}",
                        icon_name="color-management-symbolic",
                        action=lambda: self._set_matugen_state(True),
                        relevance=0.9,
                        plugin_name=self.display_name,
                        data={
                            "action": "matugen_on",
                            "bypass_max_results": True,
                            "keep_launcher_open": True,
                        },
                    )
                )
            elif query.strip() == "matugen off" or query.strip() == "matugen disable":
                # Show result for disabling matugen (execute on Enter)
                results.append(
                    Result(
                        title=f"Disable Matugen{indicator_text}",
                        subtitle=f"Turn off dynamic color generation • {status_text}",
                        icon_name="color-management-symbolic",
                        action=lambda: self._set_matugen_state(False),
                        relevance=0.9,
                        plugin_name=self.display_name,
                        data={
                            "action": "matugen_off",
                            "bypass_max_results": True,
                            "keep_launcher_open": True,
                        },
                    )
                )
            elif query.strip() == "matugen toggle":
                # Show result for toggling matugen (execute on Enter)
                new_state = not current_state
                results.append(
                    Result(
                        title=f"Toggle Matugen to {
                            'Enabled' if new_state else 'Disabled'
                        }{indicator_text}",
                        subtitle=f"Switch matugen to {
                            'enabled' if new_state else 'disabled'
                        } • {status_text}",
                        icon_name="color-management-symbolic",
                        action=lambda: self._set_matugen_state(new_state),
                        relevance=0.9,
                        plugin_name=self.display_name,
                        data={
                            "action": "matugen_toggle",
                            "bypass_max_results": True,
                            "keep_launcher_open": True,
                        },
                    )
                )
            elif ("on" in query or "enable" in query) and not query.strip().endswith(
                ("on", "enable")
            ):
                # Show suggestion for enabling (partial match)
                results.append(
                    Result(
                        title=f"Enable Matugen{indicator_text}",
                        subtitle=f"Turn on dynamic color generation • {status_text}",
                        icon_name="color-management-symbolic",
                        action=lambda: self._set_matugen_state(True),
                        relevance=0.8,
                        plugin_name=self.display_name,
                        data={
                            "action": "matugen_on_suggestion",
                            "bypass_max_results": True,
                            "keep_launcher_open": True,
                        },
                    )
                )
            elif ("off" in query or "disable" in query) and not query.strip().endswith(
                ("off", "disable")
            ):
                # Show suggestion for disabling (partial match)
                results.append(
                    Result(
                        title=f"Disable Matugen{indicator_text}",
                        subtitle=f"Turn off dynamic color generation • {status_text}",
                        icon_name="color-management-symbolic",
                        action=lambda: self._set_matugen_state(False),
                        relevance=0.8,
                        plugin_name=self.display_name,
                        data={
                            "action": "matugen_off_suggestion",
                            "bypass_max_results": True,
                            "keep_launcher_open": True,
                        },
                    )
                )
            elif "toggle" in query and not query.strip().endswith("toggle"):
                # Show suggestion for toggling (partial match)
                results.append(
                    Result(
                        title=f"Toggle Matugen{indicator_text}",
                        subtitle=f"Switch matugen state • {status_text}",
                        icon_name="color-management-symbolic",
                        action=lambda: self._set_matugen_state(not current_state),
                        relevance=0.8,
                        plugin_name=self.display_name,
                        data={
                            "action": "matugen_toggle_suggestion",
                            "bypass_max_results": True,
                            "keep_launcher_open": True,
                        },
                    )
                )
            else:
                # Show current state with scheme info
                results.append(
                    Result(
                        title=f"Matugen: {'Enabled' if current_state else 'Disabled'}{
                            indicator_text
                        }",
                        subtitle=f"Dynamic colors • {status_text}",
                        icon_name="color-management-symbolic",
                        action=lambda: None,
                        relevance=0.8,
                        plugin_name=self.display_name,
                        data={"action": "matugen_status", "bypass_max_results": True},
                    )
                )

        # Status command
        if query == "status" or query == "info":
            results.append(
                Result(
                    title=f"Wallpaper System Status{indicator_text}",
                    subtitle=status_text,
                    icon_name="color-management-symbolic",
                    action=lambda: None,
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={"action": "status", "bypass_max_results": True},
                )
            )

            # Show quick actions
            results.append(
                Result(
                    title=f"Random Wallpaper{indicator_text}",
                    subtitle=f"Set a random wallpaper • {status_text}",
                    icon_name="media-playlist-shuffle-symbolic",
                    action=lambda: self._set_random_wallpaper(),
                    relevance=0.9,
                    plugin_name=self.display_name,
                    data={
                        "action": "random_quick",
                        "bypass_max_results": True,
                        "keep_launcher_open": True,
                    },
                )
            )

        # Search wallpapers by filename - Show ALL wallpapers like example_wallpapers.py
        if not query or (
            query
            and "matugen" not in query
            and "random" not in query
            and "scheme" not in query
            and "status" not in query
            and "info" not in query
        ):
            matching_wallpapers = []
            for wallpaper in self.wallpapers:
                if not query or query in wallpaper.lower():
                    # Calculate relevance
                    relevance = 1.0 if query == wallpaper.lower() else 0.7
                    if query and query in wallpaper.lower():
                        relevance = 0.8
                    matching_wallpapers.append((wallpaper, relevance))

            # Sort by relevance and show ALL wallpapers (like example_wallpapers.py)
            matching_wallpapers.sort(key=lambda x: x[1], reverse=True)

            # Show ALL wallpapers instead of limiting (following example_wallpapers.py pattern)
            for wallpaper, relevance in matching_wallpapers:
                # Use fast thumbnail loading
                icon = self._get_thumbnail_fast(wallpaper)

                results.append(
                    Result(
                        title=f"{wallpaper}{indicator_text if not query else ''}",
                        subtitle=f"Set as wallpaper{
                            ' • ' + status_text if not query else ''
                        }",
                        icon=icon,
                        icon_name="image-x-generic-symbolic" if not icon else None,
                        action=lambda w=wallpaper: self._set_wallpaper(w),
                        relevance=relevance,
                        plugin_name=self.display_name,
                        data={
                            "wallpaper": wallpaper,
                            "action": "set",
                            "bypass_max_results": True,
                            "keep_launcher_open": True,
                        },
                    )
                )

        # Sort by relevance - no limit since we use bypass_max_results
        results.sort(key=lambda x: x.relevance, reverse=True)
        return results
