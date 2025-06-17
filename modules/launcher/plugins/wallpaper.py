"""
Wallpaper plugin for the launcher.
Provides wallpaper management with search, random selection, matugen integration, and hex color support.
"""

import os
import random
import hashlib
import colorsys
import re
from typing import List, Dict
from PIL import Image
from gi.repository import GdkPixbuf
from modules.launcher.plugin_base import PluginBase
from modules.launcher.result import Result
from fabric.utils.helpers import exec_shell_command_async
import config.data as data
import utils.icons as icons


class WallpaperPlugin(PluginBase):
    """
    Plugin for wallpaper management with search, random selection, and matugen integration.
    """

    def __init__(self):
        super().__init__()
        self.wallpapers = []
        self.cache_dir = f"{data.CACHE_DIR}/thumbs"
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
        self.set_triggers(["wall", "wall "])
        self._load_wallpapers()
        os.makedirs(self.cache_dir, exist_ok=True)

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
        """Get current matugen state from file."""
        try:
            if os.path.exists(data.MATUGEN_STATE_FILE):
                with open(data.MATUGEN_STATE_FILE, "r") as f:
                    content = f.read().strip().lower()
                    return content == "true"
            return True  # Default to True
        except Exception as e:
            print(f"Error reading matugen state: {e}")
            return True

    def _set_matugen_state(self, enabled: bool):
        """Set matugen state to file."""
        try:
            os.makedirs(os.path.dirname(data.MATUGEN_STATE_FILE), exist_ok=True)
            with open(data.MATUGEN_STATE_FILE, "w") as f:
                f.write("true" if enabled else "false")
            # Show notification for immediate feedback
            status = "enabled" if enabled else "disabled"
            exec_shell_command_async(
                f"notify-send '🎨 Matugen' 'Dynamic colors {status}' -a '{
                    data.APP_NAME_CAP
                }' -e"
            )
        except Exception as e:
            print(f"Error setting matugen state: {e}")

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
                    # Use faster thumbnail creation
                    img.thumbnail((48, 48), Image.Resampling.LANCZOS)
                    img.save(cache_path, "PNG")
            except Exception as e:
                print(f"Error creating thumbnail for {filename}: {e}")
                return None

        return cache_path

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

        # Show notification with matugen status
        if matugen_enabled:
            exec_shell_command_async(
                f"notify-send '🎨 Color Scheme' 'Set to {
                    scheme_name
                }\\nMatugen: Enabled' -a '{data.APP_NAME_CAP}' -e"
            )
        else:
            exec_shell_command_async(
                f"notify-send '⚠️ Color Scheme' 'Set to {
                    scheme_name
                }\\nMatugen: Disabled (enable for effect)' -a '{data.APP_NAME_CAP}' -e"
            )

    def _apply_hex_color(self, hex_color: str, scheme: str = None):
        """Apply hex color using matugen."""
        if not hex_color.startswith("#"):
            hex_color = "#" + hex_color

        if scheme is None:
            scheme = self._get_current_scheme()

        exec_shell_command_async(f'matugen color hex "{hex_color}" -t {scheme}')
        scheme_name = self.schemes.get(scheme, scheme)
        exec_shell_command_async(
            f"notify-send '🎨 Hex Color Applied' 'Color: {hex_color}\\nScheme: {
                scheme_name
            }' -a '{data.APP_NAME_CAP}' -e"
        )

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
        if query == "random" or query.startswith("random"):
            # Execute immediately when this result is created/selected
            self._set_random_wallpaper()
            results.append(
                Result(
                    title=f"Random Wallpaper Applied{indicator_text}",
                    subtitle=f"A random wallpaper has been set • {status_text}",
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
                    action=lambda: None,  # No action needed since already executed
                    relevance=1.0,
                    plugin_name=self.display_name,
                    data={
                        "action": "random",
                        "executed": True,
                        "bypass_max_results": True,
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
                # Execute immediately
                self._apply_hex_color(hex_color, scheme)
                scheme_name = self.schemes.get(scheme, scheme)
                results.append(
                    Result(
                        title=f"Hex Color Applied: {hex_color}{indicator_text}",
                        subtitle=f"Applied with {scheme_name} scheme • {status_text}",
                        icon_markup=icons.palette,
                        action=lambda: None,  # No action needed since already executed
                        relevance=1.0,
                        plugin_name=self.display_name,
                        data={
                            "action": "hex_color",
                            "color": hex_color,
                            "scheme": scheme,
                            "executed": True,
                            "bypass_max_results": True,
                        },
                    )
                )
            elif "random" in query:
                # Random hex color
                hex_color = self._generate_random_hex_color()
                self._apply_hex_color(hex_color, scheme)
                scheme_name = self.schemes.get(scheme, scheme)
                results.append(
                    Result(
                        title=f"Random Color Applied: {hex_color}{indicator_text}",
                        subtitle=f"Applied with {scheme_name} scheme • {status_text}",
                        icon_markup=icons.palette,
                        action=lambda: None,  # No action needed since already executed
                        relevance=1.0,
                        plugin_name=self.display_name,
                        data={
                            "action": "random_hex",
                            "color": hex_color,
                            "scheme": scheme,
                            "executed": True,
                            "bypass_max_results": True,
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
                            },
                        )
                    )

        # Matugen controls
        if "matugen" in query:
            current_state = self._get_matugen_state()
            if "on" in query or "enable" in query:
                # Execute immediately
                self._set_matugen_state(True)
                # Get updated status after change
                new_indicator_text, new_status_text, _, _ = (
                    self._get_status_indicators()
                )
                results.append(
                    Result(
                        title=f"Matugen Enabled{new_indicator_text}",
                        subtitle=f"Dynamic color generation is now enabled • {
                            new_status_text
                        }",
                        icon_markup=icons.palette,
                        action=lambda: None,  # No action needed since already executed
                        relevance=0.9,
                        plugin_name=self.display_name,
                        data={
                            "action": "matugen_on",
                            "executed": True,
                            "bypass_max_results": True,
                        },
                    )
                )
            elif "off" in query or "disable" in query:
                # Execute immediately
                self._set_matugen_state(False)
                # Get updated status after change
                new_indicator_text, new_status_text, _, _ = (
                    self._get_status_indicators()
                )
                results.append(
                    Result(
                        title=f"Matugen Disabled{new_indicator_text}",
                        subtitle=f"Dynamic color generation is now disabled • {
                            new_status_text
                        }",
                        icon_markup=icons.palette,
                        action=lambda: None,  # No action needed since already executed
                        relevance=0.9,
                        plugin_name=self.display_name,
                        data={
                            "action": "matugen_off",
                            "executed": True,
                            "bypass_max_results": True,
                        },
                    )
                )
            elif "toggle" in query:
                # Execute toggle immediately
                new_state = not current_state
                self._set_matugen_state(new_state)
                # Get updated status after change
                new_indicator_text, new_status_text, _, _ = (
                    self._get_status_indicators()
                )
                results.append(
                    Result(
                        title=f"Matugen {'Enabled' if new_state else 'Disabled'}{
                            new_indicator_text
                        }",
                        subtitle=f"Dynamic color generation is now {
                            'enabled' if new_state else 'disabled'
                        } • {new_status_text}",
                        icon_markup=icons.palette,
                        action=lambda: None,  # No action needed since already executed
                        relevance=0.9,
                        plugin_name=self.display_name,
                        data={
                            "action": "matugen_toggle",
                            "executed": True,
                            "bypass_max_results": True,
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
                    data={"action": "random_quick", "bypass_max_results": True},
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

            # Sort by relevance - no limit since we use bypass_max_results
            matching_wallpapers.sort(key=lambda x: x[1], reverse=True)

            for wallpaper, relevance in matching_wallpapers:
                # Only create thumbnails for displayed results
                cache_path = self._get_cache_path(wallpaper)
                icon = None

                # Try to load existing thumbnail first
                if os.path.exists(cache_path):
                    try:
                        icon = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                            cache_path, 32, 32, True
                        )
                    except Exception as e:
                        print(f"Error loading existing thumbnail: {e}")

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
                        },
                    )
                )

        # Sort by relevance - no limit since we use bypass_max_results
        results.sort(key=lambda x: x.relevance, reverse=True)
        return results
