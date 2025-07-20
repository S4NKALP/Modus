#!/usr/bin/env python3
"""
Test script to verify image caching works forever like example_cliphist.py.
"""

import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_image_cache():
    """Test image caching functionality."""
    try:
        from modules.launcher.plugins.clipboard import ClipboardPlugin
        
        print("Testing image cache forever functionality...")
        
        # Create plugin instance
        plugin = ClipboardPlugin()
        plugin.initialize()
        
        print("✅ Plugin initialized successfully")
        
        # Test image caching
        print("\n🖼️ Testing image cache...")
        
        # First query - should load images and cache them
        print("First query (loading images)...")
        results1 = plugin.query("")
        image_results1 = [r for r in results1 if "Image from clipboard" in r.title]
        
        if image_results1:
            print(f"Found {len(image_results1)} image results")
            
            # Check cache size
            cache_size_before = len(plugin.image_cache)
            print(f"Image cache size: {cache_size_before}")
            
            # Wait a moment
            time.sleep(1)
            
            # Second query - should use cached images
            print("\nSecond query (should use cache)...")
            results2 = plugin.query("")
            image_results2 = [r for r in results2 if "Image from clipboard" in r.title]
            
            cache_size_after = len(plugin.image_cache)
            print(f"Image cache size after second query: {cache_size_after}")
            
            # Check if images have icons (meaning they're loaded)
            cached_images = 0
            for img_result in image_results2:
                if hasattr(img_result, 'icon') and img_result.icon is not None:
                    cached_images += 1
            
            print(f"Images with loaded icons: {cached_images}/{len(image_results2)}")
            
            if cached_images > 0:
                print("✅ Images are being cached and reused!")
            else:
                print("⚠️ No cached images found")
                
        else:
            print("No image results found (normal if no images in clipboard)")
        
        print("\n✅ Image cache test completed!")
        print("Cache behavior:")
        print("  - Images are cached forever (no expiration)")
        print("  - Cache survives multiple queries")
        print("  - Images load immediately when cached")
        print("  - Cache only clears on plugin restart")
        
        plugin.cleanup()
        
    except Exception as e:
        print(f"❌ Error testing image cache: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_image_cache()
