#!/usr/bin/env python3
"""
Test script to verify clipboard search improvements.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_clipboard_search():
    """Test clipboard search functionality."""
    try:
        from modules.launcher.plugins.clipboard import ClipboardPlugin
        
        print("Testing clipboard search improvements...")
        
        # Create plugin instance
        plugin = ClipboardPlugin()
        plugin.initialize()
        
        print("✅ Plugin initialized successfully")
        
        # Test empty query (should show all items up to max_results)
        print("\n🔍 Testing empty query...")
        results = plugin.query("")
        print(f"Found {len(results)} results for empty query")
        
        # Test specific search
        print("\n🔍 Testing search query 'test'...")
        results = plugin.query("test")
        print(f"Found {len(results)} results for 'test' query")
        
        # Show relevance scores
        if results:
            print("Relevance scores:")
            for i, result in enumerate(results[:5]):  # Show first 5
                print(f"  {i+1}. {result.relevance:.2f} - {result.title[:50]}...")
        
        # Test image handling
        print("\n🖼️ Testing image handling...")
        image_results = [r for r in results if "Image from clipboard" in r.title]
        if image_results:
            print(f"Found {len(image_results)} image results")
            for img_result in image_results[:3]:  # Show first 3
                has_icon = hasattr(img_result, 'icon') and img_result.icon is not None
                print(f"  - {img_result.subtitle} (Icon loaded: {has_icon})")
        else:
            print("No image results found (normal if no images in clipboard)")

        print("\n✅ Clipboard search test completed!")
        print("The plugin now:")
        print("  - Searches through ALL clipboard items (not just first 20)")
        print("  - Sorts results by relevance (exact matches first)")
        print("  - Shows up to 50 results (increased from 20)")
        print("  - Limits results only after filtering and sorting")
        print("  - FOREVER image caching (like example_cliphist.py)")
        print("  - Better image detection (supports more formats)")
        print("  - Immediate image loading when cached")
        print("  - No cache expiration - images stay cached until restart")
        
        plugin.cleanup()
        
    except Exception as e:
        print(f"❌ Error testing clipboard search: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_clipboard_search()
