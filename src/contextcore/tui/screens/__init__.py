"""TUI Screen definitions for ContextCore interface."""

__all__ = []

try:
    from .welcome import WelcomeScreen
    from .install import InstallScreen
    from .status import StatusScreen
    from .configure import ConfigureScreen
    from .help import HelpScreen
    from .script_generator import ScriptGeneratorScreen

    __all__ = [
        "WelcomeScreen",
        "InstallScreen",
        "StatusScreen",
        "ConfigureScreen",
        "HelpScreen",
        "ScriptGeneratorScreen",
    ]
except ImportError:
    # Graceful fallback when Textual not available
    pass
