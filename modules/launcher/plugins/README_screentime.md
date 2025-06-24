# Digital Wellbeing Plugin

The Digital Wellbeing plugin provides comprehensive screen time tracking and statistics, inspired by GNOME 48's Digital Wellbeing feature. It monitors application usage and displays beautiful, modern statistics in the Modus launcher.

## Features

- **🎯 GNOME-style Interface**: Modern, clean design matching GNOME 48's Digital Wellbeing
- **📊 Comprehensive Statistics**: Large time display, summary cards, and grid-based app display
- **⏱️ Real-time Tracking**: Monitors active windows using Hyprland's `hyprctl` commands
- **🎯 Real Application Icons**: Shows actual application icons from system icon theme
- **📱 Grid Layout**: Applications displayed in a clean 3-column grid format
- **📅 Weekly Insights**: Compare daily usage with weekly averages and trends
- **🔍 Smart Search**: Find specific app usage with enhanced details and real icons
- **💾 Persistent Data**: Stores usage data in JSON files for historical tracking
- **🎨 Compact Design**:
  - Real application icons (32px) optimized for launcher
  - Clean 3-column grid layout (540x250px)
  - Compact card design (80x70px) with hover effects
  - Usage time display (no percentages for cleaner look)
  - Optimized for launcher's 550x260 scroll window

## Usage

### Trigger Keywords
- `screentime` - Show full screen time statistics
- `st` - Short alias for screen time

### Commands
- `screentime` or `st` - Display compact Digital Wellbeing summary
- `st list` - Show detailed app usage grid
- `st apps` - Same as list (alternative command)
- `st week` - Display weekly statistics and trends
- `st <app_name>` - Search for specific application with weekly comparison

### Examples
```
screentime          # Compact summary (header + cards only)
st                  # Short alias for compact view
st list             # Full app usage grid
st apps             # Alternative for app list
st week             # Weekly statistics
st firefox          # Firefox usage details
st code             # VS Code usage details
```

## Interface Components

### 🏠 Main Dashboard (Default View)
- **Large Time Display**: Prominent display of total screen time today
- **Summary Cards**:
  - Most Used App with time spent
  - Total Apps Used count
  - Average Session Length per app
- **Compact Layout**: Clean summary without app grid (540x150px)

### 📱 App List View (`st list`)
- **Full App Grid**: Top 12 applications displayed in a 3-column grid layout
- **Detailed View**: Shows individual app icons, names, and usage times
- **Expanded Layout**: Larger widget (540x250px) to accommodate grid

### 📊 Statistics Display
- **Real Application Icons**: Displays actual application icons from system theme
- **Usage Comparison**: Compare today vs yesterday with difference indicators
- **Weekly Averages**: Show daily averages for each application
- **Compact Grid Layout**:
  - 32px application icons optimized for launcher
  - 3-column grid layout (80x70px cards)
  - App name and usage time display (no percentages)
  - Automatic fallback to default application icon
  - Icon caching for improved performance
- **Launcher-Optimized Design**:
  - Fits perfectly in launcher's 550x260 scroll window
  - Compact card layout with minimal spacing
  - Hover effects for better interactivity
  - Clean, uncluttered information display

## Data Storage

Usage data is stored in `config/json/screentime/` directory:
- `usage_YYYY-MM-DD.json` - Daily usage data files
- Data includes application class names and total seconds used
- Automatic cleanup of old data (configurable retention period)
- Weekly aggregation for trend analysis

## How It Works

1. **Window Tracking**: Uses `hyprctl -j activewindow` to detect the currently focused application
2. **Time Recording**: Tracks time spent in each application by monitoring window focus changes
3. **Data Persistence**: Saves usage data every 30 seconds and on plugin cleanup
4. **Visualization**: Creates custom GTK widgets with progress bars to show usage statistics

## Technical Details

- **Background Monitoring**: Runs a background thread that checks active window every 2 seconds
- **Application Detection**: Uses window class names from Hyprland for application identification
- **Memory Efficient**: Only stores essential data and cleans up old cache entries
- **Error Handling**: Gracefully handles window manager errors and missing data

## Customization

The plugin can be customized by modifying:
- Update frequency (currently 2 seconds)
- Number of top applications shown (currently 10)
- Minimum usage time threshold (currently 1 minute)
- Bar graph colors and styling in `styles/launcher.css`

## CSS Classes

The plugin uses these CSS classes for modern GNOME-style styling:
- `#screentime-widget` - Main widget container with rounded corners
- `.screentime-title` - Main title styling
- `.screentime-time-display` - Large time display with custom font
- `.screentime-card` - Summary cards with hover effects
- `.screentime-app-item` - Individual app items with modern styling
- `.screentime-app-icon` - App icon placeholders with gradients
- `.screentime-progress` - Modern progress bars with gradients
- `.screentime-progress.high-usage` - High usage bars (red gradient)
- `.screentime-progress.medium-usage` - Medium usage bars (yellow gradient)
- `.screentime-progress.low-usage` - Low usage bars (green gradient)

## Requirements

- Hyprland window manager
- `hyprctl` command available in PATH
- GTK 3.0
- Python 3.7+

## Privacy

- All data is stored locally on your system
- No network connections or external data sharing
- Data files can be manually deleted if desired
