# AGENTS.md - Modus Desktop Environment

## Project Overview
- **Technology**: Python desktop environment using Fabric framework (GTK/PyGObject)
- **Purpose**: Wayland desktop environment with launcher, panel, dock, notifications
- **Entry Point**: `main.py` - starts all components
- **Dependencies**: PyGObject, loguru, pillow, psutil, pydbus - see requirements.txt

## Build/Test Commands
- **Run Application**: `python main.py`
- **Test Icon Browser**: `python test.py` 
- **Install Dependencies**: `pip install -r requirements.txt`
- **No formal test suite exists** - test by running individual modules/components directly

## Code Style Guidelines
- **Import Order**: Standard library first, third-party (gi, fabric), local modules last with blank lines
- **Import Comments**: Use `# Standard library imports`, `# Fabric imports`, `# Local imports` headers
- **Formatting**: PEP 8, 4 spaces indentation, line length ~100 chars
- **Naming**: snake_case functions/variables, PascalCase classes, UPPER_CASE constants
- **Type Hints**: Use modern typing (list[str] over List[str]), Optional for nullable params
- **Error Handling**: try/except with contextlib.suppress for optional operations, log with loguru
- **Documentation**: Brief docstrings for classes, avoid inline comments unless complex
- **Constants**: Module-level constants at top after imports (APP_NAME, ALLOWED_PLAYERS)
- **Services**: Use @Property/@Signal decorators, inherit from fabric.core.service.Service
- **Widgets**: Inherit from fabric.widgets (Window, Box, Entry), use **kwargs forwarding
- **GTK**: Always use gi.require_version before imports, handle missing dependencies gracefully