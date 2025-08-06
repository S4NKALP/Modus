# AGENTS.md - Modus Desktop Environment

## Project Overview
- **Technology**: Python desktop environment using Fabric framework (GTK/PyGObject)
- **Purpose**: Wayland desktop environment with launcher, panel, dock, notifications
- **Entry Point**: `main.py` - starts all components

## Build/Test Commands
- **Run Application**: `python main.py`
- **Test Icon Browser**: `python test.py` 
- **Install Dependencies**: `pip install -r requirements.txt`
- **No formal test suite exists** - test by running components directly

## Code Style Guidelines
- **Imports**: Standard library first, third-party second, local modules last with blank lines between groups
- **Formatting**: Follow PEP 8, use 4 spaces for indentation
- **Naming**: snake_case for functions/variables, PascalCase for classes, UPPER_CASE for constants
- **Type Hints**: Use typing imports for List, Optional, Tuple annotations
- **Error Handling**: Use try/except blocks, log errors with print statements or loguru logger
- **Comments**: Minimal docstrings for classes, no inline comments unless complex logic
- **Constants**: Define module-level constants at top (e.g., SEARCH_DEBOUNCE_MS = 50)
- **Properties**: Use @Property decorator with type hints for Fabric service properties
- **Signals**: Use @Signal decorator for event handling in services
- **Widget Structure**: Inherit from appropriate Fabric widgets (Window, Box, Entry, etc.)
- **GTK Integration**: Use gi.repository imports for GTK, GLib functionality