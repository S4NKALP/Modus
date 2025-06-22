import colorsys
import hashlib
import json
import os
import random
import re
import threading
import time
from typing import Dict, List, Optional

import config.data as data
import utils.icons as icons
from fabric.utils.helpers import exec_shell_command_async
from gi.repository import GdkPixbuf
from modules.launcher.plugin_base import PluginBase
from modules.launcher.result import Result
from PIL import Image


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
                print(f"Wallpapers directory not found: {data.WALLPAPERS_DIR}")
        except Exception as e:
            print(f"Error loading wallpapers: {e}")

    def _is_image(self, filename: str) -> bool:
        """Check if file is a supported image format."""
        return filename.lower().endswith(
            (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")
        )

    def _get_matugen_state(self) -> bool:
        """Get current matugen state from config.json."""
        self.matugen_enabled = True  # Default to True
        try:
            with open(data.CONFIG_FILE, "r") as f:
                config = json.load(f)
                self.matugen_enabled = config.get("matugen_enabled", True)
        except FileNotFoundError:
            # File doesn't exist, keep default True
            pass
        except Exception as e:
            print(f"Error reading config file: {e}")
            # Keep default True on error

        return self.matugen_enabled

    def _set_matugen_state(self, enabled: bool):
        """Set matugen state and save to config.json."""
        self.matugen_enabled = enabled

        # Save the state to config.json
        try:
            # Read current config
            config = {}
            if os.path.exists(data.CONFIG_FILE):
                with open(data.CONFIG_FILE, "r") as f:
                    config = json.load(f)

            # Update matugen state
            config["matugen_enabled"] = enabled

            # Write back to config file
            with open(data.CONFIG_FILE, "w") as f:
                json.dump(config, f, indent=4)

        except Exception as e:
            print(f"Error writing matugen state to config: {e}")

        # # Send notification
        # status = "enabled" if enabled else "disabled"
        # exec_shell_command_async(
        #     f"notify-send '🎨 Matugen' 'Dynamic colors {status}' -a '{
        #         data.APP_NAME_CAP
        #     }' -e"
        # )

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
                with Image.open(full_path) as img:
                    # Use faster thumbnail creation with smaller size for better performance
                    img.thumbnail((32, 32), Image.Resampling.LANCZOS)
                    img.save(cache_path, "PNG", optimize=True)
            except Exception as e:
                print(f"Error creating thumbnail for {filename}: {e}")
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
                                print(f"Error loading thumbnail for {wallpaper}: {e}")
                                self.thumbnail_cache[wallpaper] = None
                        else:
                            self.thumbnail_cache[wallpaper] = None
                    except Exception as e:
                        print(f"Error processing thumbnail for {wallpaper}: {e}")
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
                print(f"Error loading thumbnail for {filename}: {e}")
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
                            print(f"Error loading thumbnail for {filename}: {e}")
                            self.thumbnail_cache[filename] = None
                    else:
                        self.thumbnail_cache[filename] = None
                except Exception as e:
                    print(f"Error creating thumbnail for {filename}: {e}")
                    self.thumbnail_cache[filename] = None
                finally:
                    self.thumbnail_loading.discard(filename)

            thread = threading.Thread(target=create_async, daemon=True)
            thread.start()

        return None

    def _set_wallpaper(self, filename: str, scheme: str = None):
        """Set wallpaper with optional matugen integration."""
        full_path = os.path.join(data.WALLPAPERS_DIR, filename)
        current_wall = os.path.expanduser("~/.current.wall")

        if scheme is None:
            scheme = self._get_current_scheme()

        # Update current wallpaper symlink
        if os.path.isfile(current_wall) or os.path.islink(current_wall):
            os.remove(current_wall)
        os.symlink(full_path, current_wall)

        # Apply wallpaper with or without matugen
        matugen_enabled = self._get_matugen_state()
        if matugen_enabled:
            exec_shell_command_async(f'matugen image "{full_path}" -t {scheme}')
        else:
            exec_shell_command_async(
                f'swww img "{
                    full_path
                }" -t outer --transition-duration 1.5 --transition-step 255 --transition-fps 60 -f Nearest'
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

    def _hsl_to_rgb_hex(self, h: float, s: float = 1.0, l: float = 0.5) -> str:
        """Convert HSL color value to RGB HEX string."""
        # colorsys uses HLS, not HSL, and expects values between 0.0 and 1.0
        hue = h / 360.0
        r, g, b = colorsys.hls_to_rgb(hue, l, s)  # Note the order: H, L, S
        r_int, g_int, b_int = int(r * 255), int(g * 255), int(b * 255)
        return f"#{r_int:02X}{g_int:02X}{b_int:02X}"

    def _is_valid_hex_color(self, hex_color: str) -> bool:
        """Check if string is a valid hex color."""
        if not hex_color.startswith("#"):
            hex_color = "#" + hex_color
        return bool(re.match(r"^#[0-9A-Fa-f]{6}$", hex_color))

    def _get_current_scheme(self) -> str:
        """Get current color scheme (default to tonal-spot)."""
        # You could store this in a config file, for now use default
        return "scheme-tonal-spot"

    def _set_current_scheme(self, scheme: str):
        """Set current color scheme."""
        # For now, just use it immediately. Could be stored in config later.
        scheme_name = self.schemes.get(scheme, scheme)
        matugen_enabled = self._get_matugen_state()

    def _apply_hex_color(self, hex_color: str, scheme: str = None):
        """Apply hex color using matugen. Assumes matugen is enabled."""
        if not hex_color.startswith("#"):
            hex_color = "#" + hex_color

        if scheme is None:
            scheme = self._get_current_scheme()

        exec_shell_command_async(f'matugen color hex "{hex_color}" -t {scheme}')

    def _generate_random_hex_color(self) -> str:
        """Generate a random hex color."""
        hue = random.randint(0, 360)
        return self._hsl_to_rgb_hex(hue)

    def _get_status_indicators(self) -> tuple:
        """Get current status indicators for display."""
        current_scheme = self._get_current_scheme()
        matugen_enabled = self._get_matugen_state()
        scheme_name = self.schemes.get(current_scheme, current_scheme)

        indicators = []
        if not matugen_enabled:
            indicators.append("⚠ Matugen Off")

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
                    icon_markup=random.choice(
                        [
                            icons.dice_1,
                            icons.dice_2,
                            icons.dice_3,
                            icons.dice_4,
                            icons.dice_5,
                            icons.dice_6,
                        ]
                    ),
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
                    icon_markup=random.choice(
                        [
                            icons.dice_1,
                            icons.dice_2,
                            icons.dice_3,
                            icons.dice_4,
                            icons.dice_5,
                            icons.dice_6,
                        ]
                    ),
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

        # Hex color commands
        if "color" in query or "hex" in query or query.startswith("#"):
            # Check for scheme specification in the query
            scheme = self._get_current_scheme()
            for scheme_id, scheme_name in self.schemes.items():
                if (
                    scheme_name.lower() in query.lower()
                    or scheme_id.lower() in query.lower()
                ):
                    scheme = scheme_id
                    break

            # Check for hex color patterns
            hex_match = re.search(r"#?([0-9A-Fa-f]{6})", query)
            if hex_match:
                hex_color = "#" + hex_match.group(1)
                scheme_name = self.schemes.get(scheme, scheme)

                # Check if this is a complete hex color input (6 digits)
                # Execute immediately when we have a complete 6-digit hex color
                if len(hex_match.group(1)) == 6:
                    # Check if there's additional text after the hex color
                    hex_end_pos = hex_match.end()
                    remaining_text = query[hex_end_pos:].strip()

                    # Only show result if no additional text after hex color (exact match)
                    if not remaining_text:
                        # Check if matugen is enabled
                        if matugen_enabled:
                            # Show result for hex color (execute on Enter)
                            results.append(
                                Result(
                                    title=f"Apply Hex Color: {hex_color}{
                                        indicator_text
                                    }",
                                    subtitle=f"Apply with {scheme_name} scheme • {
                                        status_text
                                    }",
                                    icon_markup=icons.palette,
                                    action=lambda c=hex_color,
                                    s=scheme: self._apply_hex_color(c, s),
                                    relevance=1.0,
                                    plugin_name=self.display_name,
                                    data={
                                        "action": "hex_color",
                                        "color": hex_color,
                                        "scheme": scheme,
                                        "bypass_max_results": True,
                                        "keep_launcher_open": True,
                                    },
                                )
                            )
                        else:
                            # Show error result when matugen is disabled
                            results.append(
                                Result(
                                    title=f"Cannot Apply Hex Color: {hex_color}{
                                        indicator_text
                                    }",
                                    subtitle="Matugen is disabled • Enable matugen to use hex colors",
                                    icon_markup=icons.palette,
                                    action=lambda: None,
                                    relevance=1.0,
                                    plugin_name=self.display_name,
                                    data={
                                        "action": "hex_color_failed",
                                        "color": hex_color,
                                        "scheme": scheme,
                                        "bypass_max_results": True,
                                    },
                                )
                            )
                    else:
                        # Show suggestion for hex color with additional text (partial match)
                        results.append(
                            Result(
                                title=f"Apply Hex Color: {hex_color}{indicator_text}",
                                subtitle=f"Apply with {scheme_name} scheme • {
                                    status_text
                                }",
                                icon_markup=icons.palette,
                                action=lambda c=hex_color,
                                s=scheme: self._apply_hex_color(c, s)
                                if matugen_enabled
                                else None,
                                relevance=0.9,
                                plugin_name=self.display_name,
                                data={
                                    "action": "hex_color_suggestion",
                                    "color": hex_color,
                                    "scheme": scheme,
                                    "bypass_max_results": True,
                                    "keep_launcher_open": True,
                                },
                            )
                        )
                else:
                    # Incomplete hex color, show as suggestion
                    results.append(
                        Result(
                            title=f"Hex Color (incomplete): {hex_color}",
                            subtitle="Complete the 6-digit hex color to apply",
                            icon_markup=icons.palette,
                            action=lambda: None,
                            relevance=0.7,
                            plugin_name=self.display_name,
                            data={
                                "action": "hex_color_incomplete",
                                "color": hex_color,
                                "bypass_max_results": True,
                            },
                        )
                    )
            elif "random" in query and ("color" in query or "hex" in query):
                # Check for exact matches for random color commands
                if (
                    query.strip() == "color random"
                    or query.strip() == "hex random"
                    or query.strip() == "random color"
                    or query.strip() == "random hex"
                ):
                    # Random hex color - show result (execute on Enter)
                    scheme_name = self.schemes.get(scheme, scheme)

                    # Check if matugen is enabled
                    if matugen_enabled:
                        results.append(
                            Result(
                                title=f"Random Hex Color{indicator_text}",
                                subtitle=f"Generate and apply random color with {
                                    scheme_name
                                } scheme • {status_text}",
                                icon_markup=icons.palette,
                                action=lambda s=scheme: self._apply_hex_color(
                                    self._generate_random_hex_color(), s
                                ),
                                relevance=1.0,
                                plugin_name=self.display_name,
                                data={
                                    "action": "random_hex",
                                    "scheme": scheme,
                                    "bypass_max_results": True,
                                    "keep_launcher_open": True,
                                },
                            )
                        )
                    else:
                        # Show error result when matugen is disabled
                        results.append(
                            Result(
                                title=f"Cannot Apply Random Color{indicator_text}",
                                subtitle="Matugen is disabled • Enable matugen to use hex colors",
                                icon_markup=icons.palette,
                                action=lambda: None,
                                relevance=1.0,
                                plugin_name=self.display_name,
                                data={
                                    "action": "random_hex_failed",
                                    "bypass_max_results": True,
                                },
                            )
                        )
                else:
                    # Show suggestion for random hex color (partial match)
                    results.append(
                        Result(
                            title=f"Random Hex Color{indicator_text}",
                            subtitle=f"Generate and apply random color • {status_text}",
                            icon_markup=icons.palette,
                            action=lambda: self._apply_hex_color(
                                self._generate_random_hex_color(), scheme
                            )
                            if matugen_enabled
                            else None,
                            relevance=0.8,
                            plugin_name=self.display_name,
                            data={
                                "action": "random_hex_suggestion",
                                "bypass_max_results": True,
                                "keep_launcher_open": True,
                            },
                        )
                    )
            else:
                # Show hex color help
                results.append(
                    Result(
                        title="Hex Color Commands",
                        subtitle="Use: color #FF5733, hex #00FF00, color random, or add scheme name",
                        icon_markup=icons.palette,
                        action=lambda: None,
                        relevance=0.8,
                        plugin_name=self.display_name,
                        data={"action": "hex_help", "bypass_max_results": True},
                    )
                )

        # Color scheme commands
        if "scheme" in query:
            current_scheme = self._get_current_scheme()
            matugen_enabled = self._get_matugen_state()

            # Show all available schemes
            for scheme_id, scheme_name in self.schemes.items():
                # Check if this scheme matches the query (for filtering)
                if (
                    query.strip() == "scheme"
                    or scheme_name.lower() in query.lower()
                    or scheme_id.lower() in query.lower()
                ):
                    # Create indicators
                    indicators = []
                    if scheme_id == current_scheme:
                        indicators.append("● Current")
                    if not matugen_enabled:
                        indicators.append("⚠ Matugen Off")

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
                            icon_markup=icons.palette,
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
                        icon_markup=icons.palette,
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
                        icon_markup=icons.palette,
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
                        icon_markup=icons.palette,
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
                        icon_markup=icons.palette,
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
                        icon_markup=icons.palette,
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
                        icon_markup=icons.palette,
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
                        icon_markup=icons.palette,
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
                    icon_markup=icons.palette,
                    action=lambda: None,
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={"action": "status", "bypass_max_results": True},
                )
            )

        # Handle empty query (just trigger keywords: wall, wallpaper, wp)
        if not query:
            # Show status and quick actions when just typing trigger keywords
            results.append(
                Result(
                    title=f"Wallpaper System{indicator_text}",
                    subtitle=f"{
                        status_text
                    } • Type commands: random, scheme, status, matugen",
                    icon_markup=icons.wallpapers,
                    action=lambda: None,
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={"action": "overview", "bypass_max_results": True},
                )
            )

            # Show quick actions
            results.append(
                Result(
                    title=f"Random Wallpaper{indicator_text}",
                    subtitle=f"Set a random wallpaper • {status_text}",
                    icon_markup=random.choice(
                        [
                            icons.dice_1,
                            icons.dice_2,
                            icons.dice_3,
                            icons.dice_4,
                            icons.dice_5,
                            icons.dice_6,
                        ]
                    ),
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

        # Search wallpapers by filename
        if not query or (
            query
            and "matugen" not in query
            and "random" not in query
            and "scheme" not in query
            and "status" not in query
            and "info" not in query
            and "color" not in query
            and "hex" not in query
        ):
            matching_wallpapers = []
            for wallpaper in self.wallpapers:
                if not query or query in wallpaper.lower():
                    # Calculate relevance
                    relevance = 1.0 if query == wallpaper.lower() else 0.7
                    if query and query in wallpaper.lower():
                        relevance = 0.8
                    matching_wallpapers.append((wallpaper, relevance))

            # Sort by relevance and limit results for better performance
            matching_wallpapers.sort(key=lambda x: x[1], reverse=True)

            # Limit to first 50 results for performance (can be increased if needed)
            max_results = 50 if query else 20  # Show fewer when no query to load faster
            matching_wallpapers = matching_wallpapers[:max_results]

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
                        icon_markup=icons.wallpapers if not icon else None,
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
