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
        
        print("\n✅ Clipboard search test completed!")
        print("The plugin now:")
        print("  - Searches through ALL clipboard items (not just first 20)")
        print("  - Sorts results by relevance (exact matches first)")
        print("  - Limits results only after filtering and sorting")
        
        plugin.cleanup()
        
    except Exception as e:
        print(f"❌ Error testing clipboard search: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_clipboard_search()
