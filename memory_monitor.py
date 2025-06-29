#!/usr/bin/env python3
"""
Memory Monitor Script for Modus Components
Shows memory usage for each component in the modules/ directory.
"""

import os
import sys
import time
import psutil
import subprocess
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import json
import argparse


@dataclass
class ComponentMemory:
    """Data class to store component memory information."""
    name: str
    pid: Optional[int]
    memory_mb: float
    memory_percent: float
    cpu_percent: float
    status: str
    children_count: int = 0
    children_memory_mb: float = 0.0


class ModusMemoryMonitor:
    """Monitor memory usage of Modus components."""

    def __init__(self):
        self.modus_processes = {}
        self.component_mapping = {
            # Main components from modules/
            'dock': ['dock', 'Dock'],
            'launcher': ['launcher', 'Launcher'],
            'notification_popup': ['notification', 'NotificationPopup'],
            'osd': ['osd', 'OSD'],
            'switcher': ['switcher', 'ApplicationSwitcher'],
            'corners': ['corners', 'Corners'],

            # Dock components
            'dock_applications': ['applications'],
            'dock_battery': ['battery'],
            'dock_controls': ['controls'],
            'dock_indicators': ['indicators'],
            'dock_metrics': ['metrics'],
            'dock_music_player': ['music_player', 'music'],
            'dock_notifications': ['dock_notifications'],
            'dock_workspaces': ['workspaces'],

            # Launcher plugins
            'plugin_applications': ['plugin_applications'],
            'plugin_bluetooth': ['plugin_bluetooth'],
            'plugin_bookmarks': ['plugin_bookmarks'],
            'plugin_caffeine': ['plugin_caffeine'],
            'plugin_calculator': ['plugin_calculator'],
            'plugin_calendar': ['plugin_calendar'],
            'plugin_clipboard': ['plugin_clipboard'],
            'plugin_emoji': ['plugin_emoji'],
            'plugin_kanban': ['plugin_kanban'],
            'plugin_network': ['plugin_network'],
            'plugin_otp': ['plugin_otp'],
            'plugin_password': ['plugin_password'],
            'plugin_power': ['plugin_power'],
            'plugin_process': ['plugin_process'],
            'plugin_reminders': ['plugin_reminders'],
            'plugin_screencapture': ['plugin_screencapture'],
            'plugin_system': ['plugin_system'],
            'plugin_wallpaper': ['plugin_wallpaper'],
            'plugin_websearch': ['plugin_websearch'],

            # Services
            'service_brightness': ['brightness'],
            'service_network': ['network'],
            'service_battery': ['battery_service'],
            'service_mpris': ['mpris'],
            'service_notification': ['notification_service'],
        }

    def find_modus_processes(self) -> List[psutil.Process]:
        """Find all processes related to Modus."""
        modus_processes = []

        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'ppid']):
                try:
                    info = proc.info
                    cmdline = ' '.join(info['cmdline']) if info['cmdline'] else ''

                    # Check if this is a Modus-related process
                    if (info['name'] == 'modus' or
                        'main.py' in cmdline or
                        'Modus' in cmdline or
                        any(module in cmdline.lower() for module in ['dock', 'launcher', 'notification'])):
                        modus_processes.append(proc)

                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue

        except Exception as e:
            print(f"Error finding Modus processes: {e}")

        return modus_processes

    def get_process_memory_info(self, proc: psutil.Process) -> Tuple[float, float, float]:
        """Get memory and CPU information for a process."""
        try:
            memory_info = proc.memory_info()
            memory_mb = memory_info.rss / (1024 * 1024)
            memory_percent = proc.memory_percent()
            cpu_percent = proc.cpu_percent()
            return memory_mb, memory_percent, cpu_percent
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return 0.0, 0.0, 0.0

    def categorize_process(self, proc: psutil.Process) -> str:
        """Categorize a process based on its command line and name."""
        try:
            info = proc.info
            cmdline = ' '.join(info['cmdline']) if info['cmdline'] else ''
            name = info['name'].lower()

            # Check for main process
            if 'main.py' in cmdline:
                return 'main_process'

            # Check for specific components based on command line or imports
            for component, keywords in self.component_mapping.items():
                if any(keyword.lower() in cmdline.lower() or keyword.lower() in name for keyword in keywords):
                    return component

            # Default categorization
            if 'python' in name:
                return 'python_subprocess'
            else:
                return 'other'

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return 'unknown'

    def get_component_memory_usage(self) -> Dict[str, ComponentMemory]:
        """Get memory usage for each Modus component."""
        components = {}
        modus_processes = self.find_modus_processes()

        if not modus_processes:
            print("No Modus processes found. Make sure Modus is running.")
            return components

        # Initialize CPU monitoring for better readings
        for proc in modus_processes:
            try:
                proc.cpu_percent()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Wait a bit for CPU percentage calculation
        time.sleep(0.1)

        for proc in modus_processes:
            try:
                category = self.categorize_process(proc)
                memory_mb, memory_percent, cpu_percent = self.get_process_memory_info(proc)

                if category not in components:
                    components[category] = ComponentMemory(
                        name=category,
                        pid=proc.pid,
                        memory_mb=memory_mb,
                        memory_percent=memory_percent,
                        cpu_percent=cpu_percent,
                        status=proc.status(),
                        children_count=0,
                        children_memory_mb=0.0
                    )
                else:
                    # Aggregate memory for components with multiple processes
                    existing = components[category]
                    existing.memory_mb += memory_mb
                    existing.memory_percent += memory_percent
                    existing.cpu_percent += cpu_percent
                    existing.children_count += 1
                    existing.children_memory_mb += memory_mb

                # Also check for child processes
                try:
                    children = proc.children(recursive=True)
                    for child in children:
                        child_memory_mb, child_memory_percent, child_cpu_percent = self.get_process_memory_info(child)
                        components[category].children_memory_mb += child_memory_mb
                        components[category].memory_mb += child_memory_mb
                        components[category].memory_percent += child_memory_percent
                        components[category].cpu_percent += child_cpu_percent
                        components[category].children_count += 1

                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        return components

    def get_module_file_sizes(self) -> Dict[str, float]:
        """Get file sizes for modules in the modules/ directory."""
        module_sizes = {}
        modules_dir = os.path.join(os.path.dirname(__file__), 'modules')

        if not os.path.exists(modules_dir):
            return module_sizes

        try:
            for root, _, files in os.walk(modules_dir):
                for file in files:
                    if file.endswith('.py'):
                        file_path = os.path.join(root, file)
                        try:
                            size_kb = os.path.getsize(file_path) / 1024
                            relative_path = os.path.relpath(file_path, modules_dir)
                            module_sizes[relative_path] = size_kb
                        except OSError:
                            continue
        except Exception as e:
            print(f"Error getting module file sizes: {e}")

        return module_sizes

    def print_memory_report(self, components: Dict[str, ComponentMemory],
                          module_sizes: Dict[str, float],
                          format_type: str = 'table'):
        """Print a formatted memory usage report."""
        if not components:
            print("No Modus components found running.")
            return

        total_memory = sum(comp.memory_mb for comp in components.values())
        total_cpu = sum(comp.cpu_percent for comp in components.values())

        if format_type == 'json':
            self._print_json_report(components, module_sizes, total_memory, total_cpu)
        else:
            self._print_table_report(components, module_sizes, total_memory, total_cpu)

    def _print_table_report(self, components: Dict[str, ComponentMemory],
                           module_sizes: Dict[str, float],
                           total_memory: float, total_cpu: float):
        """Print memory report in table format."""
        print("\n" + "="*80)
        print("MODUS MEMORY USAGE REPORT")
        print("="*80)

        # Sort components by memory usage
        sorted_components = sorted(components.items(), key=lambda x: x[1].memory_mb, reverse=True)

        print(f"\n{'Component':<25} {'Memory (MB)':<12} {'Memory %':<10} {'CPU %':<8} {'PID':<8} {'Status':<10}")
        print("-" * 80)

        for name, comp in sorted_components:
            print(f"{name:<25} {comp.memory_mb:>8.2f}    {comp.memory_percent:>6.2f}%   "
                  f"{comp.cpu_percent:>5.2f}%  {comp.pid or 'N/A':<8} {comp.status:<10}")

            if comp.children_count > 0:
                print(f"  └─ Children: {comp.children_count} processes, "
                      f"{comp.children_memory_mb:.2f} MB")

        print("-" * 80)
        print(f"{'TOTAL':<25} {total_memory:>8.2f}    {'-':<10} {total_cpu:>5.2f}%")

        # Module file sizes
        if module_sizes:
            print(f"\n{'MODULE FILE SIZES':<25} {'Size (KB)':<12}")
            print("-" * 40)
            sorted_modules = sorted(module_sizes.items(), key=lambda x: x[1], reverse=True)
            for module, size in sorted_modules[:10]:  # Top 10 largest files
                print(f"{module:<25} {size:>8.2f}")

        print("\n" + "="*80)

    def _print_json_report(self, components: Dict[str, ComponentMemory],
                          module_sizes: Dict[str, float],
                          total_memory: float, total_cpu: float):
        """Print memory report in JSON format."""
        report = {
            'timestamp': time.time(),
            'total_memory_mb': round(total_memory, 2),
            'total_cpu_percent': round(total_cpu, 2),
            'components': {},
            'module_file_sizes_kb': module_sizes
        }

        for name, comp in components.items():
            report['components'][name] = {
                'memory_mb': round(comp.memory_mb, 2),
                'memory_percent': round(comp.memory_percent, 2),
                'cpu_percent': round(comp.cpu_percent, 2),
                'pid': comp.pid,
                'status': comp.status,
                'children_count': comp.children_count,
                'children_memory_mb': round(comp.children_memory_mb, 2)
            }

        print(json.dumps(report, indent=2))

    def monitor_continuously(self, interval: int = 5, format_type: str = 'table'):
        """Monitor memory usage continuously."""
        try:
            while True:
                os.system('clear' if os.name == 'posix' else 'cls')
                components = self.get_component_memory_usage()
                module_sizes = self.get_module_file_sizes()
                self.print_memory_report(components, module_sizes, format_type)
                print(f"\nRefreshing every {interval} seconds... (Press Ctrl+C to stop)")
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\nMonitoring stopped.")

    def get_memory_summary(self) -> Dict[str, float]:
        """Get a summary of memory usage by category."""
        components = self.get_component_memory_usage()

        summary = {
            'main_components': 0.0,
            'dock_components': 0.0,
            'launcher_plugins': 0.0,
            'services': 0.0,
            'other': 0.0
        }

        for name, comp in components.items():
            if name in ['main_process', 'dock', 'launcher', 'notification_popup', 'osd', 'switcher', 'corners']:
                summary['main_components'] += comp.memory_mb
            elif name.startswith('dock_'):
                summary['dock_components'] += comp.memory_mb
            elif name.startswith('plugin_'):
                summary['launcher_plugins'] += comp.memory_mb
            elif name.startswith('service_'):
                summary['services'] += comp.memory_mb
            else:
                summary['other'] += comp.memory_mb

        return summary


def main():
    """Main function to run the memory monitor."""
    parser = argparse.ArgumentParser(description='Monitor memory usage of Modus components')
    parser.add_argument('--format', choices=['table', 'json'], default='table',
                       help='Output format (default: table)')
    parser.add_argument('--monitor', action='store_true',
                       help='Monitor continuously')
    parser.add_argument('--interval', type=int, default=5,
                       help='Refresh interval in seconds for continuous monitoring (default: 5)')
    parser.add_argument('--summary', action='store_true',
                       help='Show only summary by category')

    args = parser.parse_args()

    monitor = ModusMemoryMonitor()

    if args.monitor:
        monitor.monitor_continuously(args.interval, args.format)
    elif args.summary:
        summary = monitor.get_memory_summary()
        print("\nMODUS MEMORY SUMMARY BY CATEGORY")
        print("="*40)
        total = sum(summary.values())
        for category, memory in summary.items():
            percentage = (memory / total * 100) if total > 0 else 0
            print(f"{category.replace('_', ' ').title():<20} {memory:>8.2f} MB ({percentage:>5.1f}%)")
        print("-"*40)
        print(f"{'Total':<20} {total:>8.2f} MB")
    else:
        components = monitor.get_component_memory_usage()
        module_sizes = monitor.get_module_file_sizes()
        monitor.print_memory_report(components, module_sizes, args.format)


if __name__ == '__main__':
    main()