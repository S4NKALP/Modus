import os
import hashlib
import time
import uuid

from fabric.utils import get_relative_path
from gi.repository import GdkPixbuf
from loguru import logger

import config.data as data

# Unified notification cache directory (for both app icons and notification images)
UNIFIED_NOTIFICATION_CACHE_DIR = os.path.join(data.CACHE_DIR, "notifications")


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
            
            # Create hash from file path and size
            hash_input = source_data
            if size:
                hash_input += f"_{size[0]}x{size[1]}"
            
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
            pixbuf = pixbuf.scale_simple(size[0], size[1], GdkPixbuf.InterpType.BILINEAR)

        pixbuf.savev(cache_path, "png", [], [])
        logger.debug(f"Cached notification asset: {cache_key}")
        return cache_path, cache_key
    except Exception as e:
        logger.warning(f"Failed to cache notification asset: {e}")
        return None, None


def get_from_cache(cache_key, size=None):
    """Get a cached asset or return None if not found"""
    try:
        cache_path = os.path.join(UNIFIED_NOTIFICATION_CACHE_DIR, f"{cache_key}.png")
        if os.path.exists(cache_path):
            logger.debug(f"Using cached asset: {cache_key}")
            if size:
                return GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    cache_path, size[0], size[1], True
                )
            else:
                return GdkPixbuf.Pixbuf.new_from_file(cache_path)
    except Exception as e:
        logger.warning(f"Failed to load cached asset: {e}")
    return None


def cleanup_cache(cache_key=None):
    """Clean up unified cache - specific key or all"""
    try:
        ensure_cache_dir()

        if cache_key:
            # Remove specific cached asset
            cache_path = os.path.join(UNIFIED_NOTIFICATION_CACHE_DIR, f"{cache_key}.png")
            if os.path.exists(cache_path):
                os.unlink(cache_path)
                logger.debug(f"Cleaned up cached asset: {cache_key}")
        else:
            # Remove all cached assets
            for filename in os.listdir(UNIFIED_NOTIFICATION_CACHE_DIR):
                if filename.endswith(".png"):
                    filepath = os.path.join(UNIFIED_NOTIFICATION_CACHE_DIR, filename)
                    try:
                        os.unlink(filepath)
                        logger.debug(f"Cleaned up cached asset: {filename}")
                    except Exception as e:
                        logger.warning(f"Failed to cleanup cache file {filename}: {e}")
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
                        logger.debug(f"Cleaned up old cache: {filename}")
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
                f for f in os.listdir(UNIFIED_NOTIFICATION_CACHE_DIR) if f.endswith(".png")
            ]

        logger.info(f"Cache persistence check: {len(cache_files)} assets cached")

        # Test loading a few cached items to verify they work
        for cache_file in cache_files[:2]:  # Test first 2 files
            try:
                cache_path = os.path.join(UNIFIED_NOTIFICATION_CACHE_DIR, cache_file)
                test_pixbuf = GdkPixbuf.Pixbuf.new_from_file(cache_path)
                if test_pixbuf:
                    logger.debug(f"Successfully verified cached asset: {cache_file}")
            except Exception as e:
                logger.warning(f"Failed to load cached asset {cache_file}: {e}")

        return len(cache_files) > 0

    except Exception as e:
        logger.error(f"Failed to verify cache persistence: {e}")
        return False


def get_fallback_icon(size=(48, 48)):
    """Get the fallback notification icon"""
    try:
        fallback_path = get_relative_path("../../config/assets/icons/notification.png")
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
        except:
            return None


# Initialize cache on module load
ensure_cache_dir()
cleanup_old_cache_files()
verify_cache_persistence()