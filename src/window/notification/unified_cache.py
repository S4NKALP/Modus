import hashlib
import time
import uuid
from collections import OrderedDict

from fabric.utils import GdkPixbuf, get_relative_path, Gtk, logger, os

import shared.data as data

# Unified notification cache directory (for both app icons and notification images)
UNIFIED_NOTIFICATION_CACHE_DIR = os.path.join(data.CACHE_DIR, "notifications")

_MEMORY_PIXBUF_CACHE: OrderedDict[str, GdkPixbuf.Pixbuf] = OrderedDict()
_MEMORY_CACHE_MAX = 64


def _get_icon_theme_name():
    """Get the current GTK icon theme name for cache invalidation"""
    try:
        settings = Gtk.Settings.get_default()
        if settings:
            return getattr(settings, "gtk_icon_theme_name", "") or ""
    except Exception:
        pass
    # Fallback: read from settings.ini
    try:
        settings_path = os.path.expanduser("~/.config/gtk-3.0/settings.ini")
        if os.path.exists(settings_path):
            with open(settings_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("gtk-icon-theme-name="):
                        return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return ""


def ensure_cache_dir():
    """Ensure unified notification cache directory exists"""
    os.makedirs(UNIFIED_NOTIFICATION_CACHE_DIR, exist_ok=True)


def get_unified_cache_key(source_data, size=None, app_name=None):
    """Generate a unified cache key that works for both app icons and notification images"""
    try:
        if hasattr(source_data, "get_pixels"):
            # For pixbuf data - use hash of pixel data for deterministic caching
            try:
                pixel_data = source_data.get_pixels()
                image_hash = hashlib.md5(pixel_data).hexdigest()[:8]
                return image_hash
            except Exception:
                # Fallback to random UUID if pixel data fails
                return str(uuid.uuid4())[:8]
        elif isinstance(source_data, str):
            # For file paths - create hash-based name
            if source_data.startswith("file://"):
                source_data = source_data[7:]

            # Create hash from file path, size, and icon theme
            hash_input = source_data
            if size:
                hash_input += f"_{size[0]}x{size[1]}"
            # Include icon theme so cache invalidates on theme change
            theme = _get_icon_theme_name()
            if theme:
                hash_input += f"|{theme}"

            return hashlib.md5(hash_input.encode()).hexdigest()[:8]
        else:
            # Fallback to random UUID
            return str(uuid.uuid4())[:8]
    except Exception:
        # Ultimate fallback
        return str(uuid.uuid4())[:8]


def save_to_cache(pixbuf, cache_key, size=None):
    """Save a pixbuf to the unified cache directory"""
    try:
        ensure_cache_dir()
        cache_path = os.path.join(UNIFIED_NOTIFICATION_CACHE_DIR, f"{cache_key}.png")

        # Don't overwrite existing cache
        if os.path.exists(cache_path):
            logger.debug(f"Cache hit - already exists: {cache_key}")
            return cache_path, cache_key

        # Scale if size is specified
        if size and (pixbuf.get_width() != size[0] or pixbuf.get_height() != size[1]):
            pixbuf = pixbuf.scale_simple(
                size[0], size[1], GdkPixbuf.InterpType.BILINEAR
            )

        pixbuf.savev(cache_path, "png", [], [])
        return cache_path, cache_key
    except Exception as e:
        logger.warning(f"Failed to cache notification asset: {e}")
        return None, None


def get_from_cache(cache_key, size=None):
    """Get a cached asset or return None if not found"""
    mem_key = f"{cache_key}:{size}"
    if mem_key in _MEMORY_PIXBUF_CACHE:
        _MEMORY_PIXBUF_CACHE.move_to_end(mem_key)
        return _MEMORY_PIXBUF_CACHE[mem_key]
    try:
        cache_path = os.path.join(UNIFIED_NOTIFICATION_CACHE_DIR, f"{cache_key}.png")
        if os.path.exists(cache_path):
            if size:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    cache_path, size[0], size[1], True
                )
            else:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(cache_path)
            while len(_MEMORY_PIXBUF_CACHE) >= _MEMORY_CACHE_MAX:
                _MEMORY_PIXBUF_CACHE.popitem(last=False)
            _MEMORY_PIXBUF_CACHE[mem_key] = pixbuf
            return pixbuf
    except Exception as e:
        logger.warning(f"Failed to load cached asset: {e}")
    return None


def cleanup_cache(cache_key=None):
    """Clean up unified cache - specific key or all"""
    try:
        ensure_cache_dir()

        if cache_key:
            # Remove specific cached asset
            cache_path = os.path.join(
                UNIFIED_NOTIFICATION_CACHE_DIR, f"{cache_key}.png"
            )
            if os.path.exists(cache_path):
                os.unlink(cache_path)
            mem_keys = [k for k in _MEMORY_PIXBUF_CACHE if k.startswith(cache_key)]
            for k in mem_keys:
                _MEMORY_PIXBUF_CACHE.pop(k, None)
        else:
            # Remove all cached assets
            for filename in os.listdir(UNIFIED_NOTIFICATION_CACHE_DIR):
                if filename.endswith(".png"):
                    filepath = os.path.join(UNIFIED_NOTIFICATION_CACHE_DIR, filename)
                    try:
                        os.unlink(filepath)
                    except Exception as e:
                        logger.warning(f"Failed to cleanup cache file {filename}: {e}")
            _MEMORY_PIXBUF_CACHE.clear()
    except Exception as e:
        logger.warning(f"Failed to cleanup cache: {e}")


def cleanup_old_cache_files():
    """Clean up old cache files (older than 7 days)"""
    try:
        if not os.path.exists(UNIFIED_NOTIFICATION_CACHE_DIR):
            return

        current_time = time.time()
        week_ago = current_time - (7 * 24 * 60 * 60)  # 7 days

        for filename in os.listdir(UNIFIED_NOTIFICATION_CACHE_DIR):
            filepath = os.path.join(UNIFIED_NOTIFICATION_CACHE_DIR, filename)
            try:
                if os.path.isfile(filepath):
                    file_mtime = os.path.getmtime(filepath)
                    if file_mtime < week_ago:
                        os.unlink(filepath)
            except Exception as e:
                logger.warning(f"Failed to cleanup cache file {filename}: {e}")
    except Exception as e:
        logger.warning(f"Failed to cleanup cache: {e}")


def verify_cache_persistence():
    """Verify that cached assets persist and can be loaded after restart"""
    try:
        cache_files = []

        if os.path.exists(UNIFIED_NOTIFICATION_CACHE_DIR):
            cache_files = [
                f
                for f in os.listdir(UNIFIED_NOTIFICATION_CACHE_DIR)
                if f.endswith(".png")
            ]

        # Test loading a few cached items to verify they work
        for cache_file in cache_files[:2]:  # Test first 2 files
            try:
                cache_path = os.path.join(UNIFIED_NOTIFICATION_CACHE_DIR, cache_file)
                GdkPixbuf.Pixbuf.new_from_file(cache_path)
            except Exception as e:
                logger.warning(f"Failed to load cached asset {cache_file}: {e}")

        return len(cache_files) > 0

    except Exception as e:
        logger.error(f"Failed to verify cache persistence: {e}")
        return False


def get_fallback_icon(size=(48, 48)):
    """Get the fallback notification icon"""
    try:
        fallback_path = get_relative_path("../../assets/icons/notification.png")
        return GdkPixbuf.Pixbuf.new_from_file_at_scale(
            fallback_path, size[0], size[1], True
        )
    except Exception as e:
        logger.warning(f"Failed to load fallback icon: {e}")
        # Create a simple colored rectangle as ultimate fallback
        try:
            return GdkPixbuf.Pixbuf.new(
                GdkPixbuf.Colorspace.RGB, True, 8, size[0], size[1]
            )
        except Exception:
            return None


# Theme tracking for cache invalidation
_CURRENT_THEME_FILE = os.path.join(data.CACHE_DIR, ".current_icon_theme")


def _get_stored_theme():
    """Get the previously stored icon theme name"""
    try:
        if os.path.exists(_CURRENT_THEME_FILE):
            with open(_CURRENT_THEME_FILE) as f:
                return f.read().strip()
    except Exception:
        pass
    return ""


def _store_theme(name):
    """Store the current icon theme name"""
    try:
        os.makedirs(os.path.dirname(_CURRENT_THEME_FILE), exist_ok=True)
        with open(_CURRENT_THEME_FILE, "w") as f:
            f.write(name)
    except Exception:
        pass


def cleanup_theme_changed_caches():
    """Clear notification pixbuf caches if icon theme changed since last run"""
    current_theme = _get_icon_theme_name()
    stored_theme = _get_stored_theme()

    if current_theme and stored_theme and current_theme != stored_theme:
        logger.info(
            f"[Cache] Icon theme changed: {stored_theme} -> {current_theme}, clearing notification caches"
        )
        cleanup_cache()  # clear all pixbuf caches
        # Also clear the icon resolver cache since icon names may map differently
        try:
            from utils.icon_resolver import ICON_CACHE_FILE

            if os.path.exists(ICON_CACHE_FILE):
                os.unlink(ICON_CACHE_FILE)
                logger.info("[Cache] Cleared icon resolver cache")
        except Exception:
            pass

    # Store current theme for next run
    if current_theme:
        _store_theme(current_theme)


# Initialize cache on module load
ensure_cache_dir()
cleanup_old_cache_files()
cleanup_theme_changed_caches()
verify_cache_persistence()
