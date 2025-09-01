#!/usr/bin/env python3
"""
Real-time memory monitor for debugging expanded player memory leaks.
This module provides functions to track memory usage in real-time.
"""

import psutil
import os
import gc
import threading
import time
from loguru import logger


class MemoryMonitor:
    """Real-time memory monitoring for debugging memory leaks."""

    def __init__(self):
        self.process = psutil.Process(os.getpid())
        self.baseline_memory = None
        self.last_memory = None
        self.monitoring = False
        self.monitor_thread = None

    def get_memory_usage(self):
        """Get current memory usage in MB."""
        return self.process.memory_info().rss / 1024 / 1024

    def get_memory_details(self):
        """Get detailed memory information."""
        memory_info = self.process.memory_info()
        memory_percent = self.process.memory_percent()

        return {
            "rss_mb": memory_info.rss / 1024 / 1024,
            "vms_mb": memory_info.vms / 1024 / 1024,
            "percent": memory_percent,
            "num_threads": self.process.num_threads(),
        }

    def set_baseline(self, label="Baseline"):
        """Set the baseline memory usage."""
        self.baseline_memory = self.get_memory_usage()
        logger.info(f"🎯 {label} memory: {self.baseline_memory:.1f} MB")
        return self.baseline_memory

    def log_memory_change(self, label="Memory Check", force_gc=True):
        """Log current memory usage and change from baseline."""
        if force_gc:
            gc.collect()

        current_memory = self.get_memory_usage()
        details = self.get_memory_details()

        if self.baseline_memory:
            delta = current_memory - self.baseline_memory
            logger.info(
                f"📊 {label}: {current_memory:.1f} MB (Δ: {delta:+.1f} MB) | Threads: {
                    details['num_threads']
                }"
            )
        else:
            logger.info(
                f"📊 {label}: {current_memory:.1f} MB | Threads: {
                    details['num_threads']
                }"
            )

        self.last_memory = current_memory
        return current_memory

    def log_memory_spike(self, threshold_mb=10):
        """Log if there's a significant memory increase."""
        if self.last_memory:
            current = self.get_memory_usage()
            increase = current - self.last_memory
            if increase > threshold_mb:
                logger.warning(
                    f"🚨 MEMORY SPIKE: +{increase:.1f} MB (from {self.last_memory:.1f} to {current:.1f} MB)"
                )
                return True
        return False

    def start_continuous_monitoring(self, interval_seconds=2):
        """Start continuous background monitoring."""
        if self.monitoring:
            return

        self.monitoring = True

        def monitor_loop():
            while self.monitoring:
                try:
                    self.log_memory_change("Continuous Monitor", force_gc=False)
                    time.sleep(interval_seconds)
                except Exception as e:
                    logger.error(f"Memory monitor error: {e}")
                    break

        self.monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info(
            f"🔍 Started continuous memory monitoring (every {interval_seconds}s)"
        )

    def stop_continuous_monitoring(self):
        """Stop continuous monitoring."""
        if self.monitoring:
            self.monitoring = False
            logger.info("🛑 Stopped continuous memory monitoring")


# Global memory monitor instance
memory_monitor = MemoryMonitor()

# Convenience functions for easy use


def set_memory_baseline(label="Baseline"):
    """Set memory baseline."""
    return memory_monitor.set_baseline(label)


def log_memory(label="Memory Check"):
    """Log current memory usage."""
    return memory_monitor.log_memory_change(label)


def start_memory_monitoring():
    """Start continuous memory monitoring."""
    memory_monitor.start_continuous_monitoring()


def stop_memory_monitoring():
    """Stop continuous memory monitoring."""
    memory_monitor.stop_continuous_monitoring()


def check_memory_spike():
    """Check for memory spike."""
    return memory_monitor.log_memory_spike()


# Test function


def test_memory_monitor():
    """Test the memory monitor."""
    print("Testing Memory Monitor...")
    monitor = MemoryMonitor()

    monitor.set_baseline("Test Start")

    # Simulate some memory usage
    big_list = [i for i in range(100000)]
    monitor.log_memory_change("After creating big list")

    del big_list
    monitor.log_memory_change("After deleting big list")

    print("Memory monitor test complete!")


if __name__ == "__main__":
    test_memory_monitor()
